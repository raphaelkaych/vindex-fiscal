"""Somente documentos sintéticos identificados. Não são boletos bancários reais."""
from datetime import date
from decimal import Decimal
from io import BytesIO
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from pypdf import PdfWriter
from pypdf.generic import NameObject, DictionaryObject, DecodedStreamObject
from portal.models import Company, Invoice, Installment
from portal.boleto_models import Boleto, BoletoEvent
from portal.tests import create_account
from portal.services.boletos import (validate_code, import_boleto, update_boleto, associate_boleto,
    disassociate_boleto, extract_pdf, BoletoImportError, BoletoAssociationError,
    UnconfiguredDDAConnector, DDAConnectorUnavailable)

# Conteúdo arbitrário de teste, DVs pré-calculados. SEM VALOR BANCÁRIO/FISCAL.
CHARGE='00197100000000123451234567890123456789012345'
CHARGE_1001='00192100100000123451234567890123456789012345'
CHARGE_9999='00191999900000123451234567890123456789012345'
CHARGE_ZERO='00194000000000123451234567890123456789012345'
COLLECTION10='83670000001234512345678901234567890123456789'
COLLECTION11='83890000001234512345678901234567890123456789'
REFERENCE10='83750000001234512345678901234567890123456789'
REFERENCE11='83970000001234512345678901234567890123456789'


def fictional_pdf(text='',pages=1,password=None,compressed=False):
    """PDF fictício em memória: texto simples com fonte padrão, sem artefatos reais."""
    writer=PdfWriter()
    for _ in range(pages):
        page=writer.add_blank_page(width=595,height=842)
        if text:
            font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
            page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
            escaped=text.replace('\\','\\\\').replace('(','\\(').replace(')','\\)')
            commands='BT /F1 10 Tf 40 780 Td 12 TL '+ ' '.join(f'({line}) Tj T*' for line in escaped.splitlines())+' ET'
            stream=DecodedStreamObject();stream.set_data(commands.encode('latin-1'))
            page[NameObject('/Contents')]=writer._add_object(stream.flate_encode() if compressed else stream)
    if password: writer.encrypt(password)
    buffer=BytesIO();writer.write(buffer)
    return buffer.getvalue()


class BoletoValidationTests(TestCase):
    def test_cobranca_reconstrucao_linha_e_dvs(self):
        parsed=validate_code(CHARGE)
        self.assertIsNone(parsed['amount'])
        self.assertEqual(parsed['amount_candidate'],Decimal('123.45'))
        self.assertEqual(len(parsed['digitable_line']),47)
        self.assertEqual(validate_code(parsed['digitable_line'])['barcode'],CHARGE)
        self.assertEqual(parsed['bank_code'],'001')
        for index in (4,9,43):
            invalid=CHARGE[:index]+str((int(CHARGE[index])+1)%10)+CHARGE[index+1:]
            with self.subTest(index=index),self.assertRaises(BoletoImportError): validate_code(invalid)

    def test_linha_cobranca_confere_tres_dvs_e_geral(self):
        line=validate_code(CHARGE)['digitable_line']
        for index in (9,20,31,32):
            with self.subTest(index=index),self.assertRaises(BoletoImportError):
                validate_code(line[:index]+str((int(line[index])+1)%10)+line[index+1:])

    def test_fator_reset_nao_escolhe_data_atual(self):
        expected=[('1000',CHARGE,'2025-02-22'),('1001',CHARGE_1001,'2025-02-23'),('9999',CHARGE_9999,'2049-10-13')]
        for _,code,modern in expected:
            result=validate_code(code)
            self.assertEqual(len(result['due_candidates']),2)
            self.assertEqual(result['due_candidates'][1],modern)
        self.assertEqual(validate_code(CHARGE)['due_candidates'][0],'2000-07-03')
        self.assertEqual(validate_code(CHARGE_9999)['due_candidates'][0],'2025-02-21')

    def test_fator_zero_nao_inventa_data_ou_valor_em_campo_especial(self):
        result=validate_code(CHARGE_ZERO)
        self.assertEqual(result['due_candidates'],[])
        self.assertIsNone(result['amount'])

    def test_arrecadacao_mod10_mod11_e_referencia_sem_brl(self):
        for code in (COLLECTION10,COLLECTION11,REFERENCE10,REFERENCE11):
            result=validate_code(code)
            self.assertEqual(result['kind'],'collection')
            self.assertEqual(len(result['digitable_line']),48)
            self.assertEqual(validate_code(result['digitable_line'])['barcode'],code)
            self.assertEqual(result['due_candidates'],[])
            if code[2] in '68': self.assertEqual(result['amount'],Decimal('123.45'))
            else: self.assertIsNone(result['amount'])

    def test_arrecadacao_confere_todos_blocos_e_geral(self):
        for code in (COLLECTION10,COLLECTION11):
            line=validate_code(code)['digitable_line']
            for index in (11,23,35,47):
                with self.subTest(code=code,index=index),self.assertRaises(BoletoImportError):
                    validate_code(line[:index]+str((int(line[index])+1)%10)+line[index+1:])
            with self.assertRaises(BoletoImportError): validate_code(code[:3]+str((int(code[3])+1)%10)+code[4:])

    def test_formato_estrito_nao_remove_letras_ou_corta_digitos(self):
        for value in ('0'*44,'pago '+CHARGE,CHARGE+'0',CHARGE[:-1],'123','９'*44):
            with self.subTest(value=value),self.assertRaises(BoletoImportError): validate_code(value)


class BoletoImportTests(TestCase):
    def setUp(self):
        self.user,self.workspace,self.company=create_account('boletos@example.test')
        self.other,self.other_workspace,self.other_company=create_account('other-boletos@example.test','00000002000180')
        self.data={'company':self.company,'barcode':CHARGE,'amount':'123.45','due_on':'2025-02-22',
            'payer_document':self.company.cnpj,'payer_name':'PAGADOR FICTICIO',
            'beneficiary_name':'BENEFICIARIO FICTICIO','beneficiary_document':'00000003000125','reference':'FICTICIO-001'}
        self.invoice=Invoice.objects.create(company=self.company,access_key='1'*44,number='FICTICIO',series='1',
            issuer_name='FORNECEDOR FICTICIO',issuer_cnpj='00000003000125',issued_on=date(2025,1,1),total='123.45',xml_content='<FICTICIO/>')
        self.part=Installment.objects.create(invoice=self.invoice,number='1',amount='123.45',due_on=date(2025,2,22))

    def test_importacao_idempotente_nao_gera_parcela_nem_pagamento(self):
        before=Installment.objects.count()
        item,created=import_boleto(self.workspace,self.data,actor=self.user)
        again,new=import_boleto(self.workspace,self.data)
        self.assertTrue(created);self.assertFalse(new);self.assertEqual(item.pk,again.pk)
        self.assertEqual(Installment.objects.count(),before)
        self.assertEqual(Boleto.objects.count(),1)
        self.assertEqual(item.financial_status,'unknown')
        self.assertEqual(item.validation_state,'validated')
        self.assertFalse(item.needs_review)
        self.assertEqual(item.events.count(),1)

    def test_importacao_sem_vencimento_preserva_ambiguidade(self):
        item,_=import_boleto(self.workspace,{'company':self.company,'barcode':CHARGE})
        self.assertIsNone(item.due_on)
        self.assertEqual(item.due_candidates,['2000-07-03','2025-02-22'])
        self.assertTrue(item.needs_review)

    def test_fator_valido_nao_confirma_valor_de_dez_posicoes(self):
        data={key:value for key,value in self.data.items() if key != 'amount'}
        item,_=import_boleto(self.workspace,data)
        self.assertEqual(item.due_on,date(2025,2,22))
        self.assertIsNone(item.amount)
        self.assertTrue(item.needs_review)
        self.assertIn('apenas um candidato',item.review_notes)
        self.assertIn('99.999.999,99',item.review_notes)
        revised=update_boleto(self.workspace,item,{'amount':'123.45'},actor=self.user)
        self.assertEqual(revised.amount,Decimal('123.45'))
        self.assertNotIn('apenas um candidato',revised.review_notes)
        self.assertIn('apenas um candidato',revised.events.get(action='revisado').details['review_notes_before'])

    def test_valor_alto_explicito_preservado_sem_assumir_valor_curto(self):
        item,_=import_boleto(self.workspace,{**self.data,'amount':'100000000123.45'})
        self.assertEqual(item.amount,Decimal('100000000123.45'))
        self.assertTrue(item.needs_review)
        self.assertIn('valores altos',item.review_notes)

    def test_empresa_pagador_e_allowlist_revalidados(self):
        attempts=[(self.workspace,{**self.data,'company':self.other_company},None),
            (self.workspace,self.data,[]),(self.workspace,self.data,[self.other_company]),
            (self.workspace,{**self.data,'payer_document':self.other_company.cnpj},None)]
        for workspace,data,allowed in attempts:
            with self.assertRaises(BoletoImportError): import_boleto(workspace,data,allowed_companies=allowed)
        self.assertFalse(Boleto.objects.exists())

    def test_mesmo_codigo_isolado_por_workspace(self):
        one,_=import_boleto(self.workspace,self.data)
        two,_=import_boleto(self.other_workspace,{**self.data,'company':self.other_company,'payer_document':self.other_company.cnpj})
        self.assertNotEqual(one.pk,two.pk)

    def test_valor_nao_finito_negativo_arredondamento_float_rejeitados(self):
        for amount in ('NaN','Infinity','-1','0','1.001',123.45):
            with self.subTest(amount=amount),self.assertRaises(BoletoImportError):
                import_boleto(self.workspace,{**self.data,'amount':amount})

    def test_divergencias_preservadas_e_nao_confirmam_pagamento(self):
        item,_=import_boleto(self.workspace,{**self.data,'amount':'10.00','due_on':'2026-10-20'})
        self.assertEqual(item.amount,Decimal('10.00'));self.assertEqual(item.due_on,date(2026,10,20))
        self.assertIn('diverge',item.review_notes)
        self.assertEqual(item.financial_status,'unknown')

    def test_reimportacao_conflitante_pede_revisao(self):
        import_boleto(self.workspace,self.data)
        with self.assertRaises(BoletoImportError): import_boleto(self.workspace,{**self.data,'amount':'1.00'})
        self.assertEqual(Boleto.objects.count(),1)

    def test_pdf_digital_texto_rotulado_e_arquivo_privado(self):
        line=validate_code(CHARGE)['digitable_line']
        text='FICTICIO - SEM VALOR BANCARIO\n'+line+'\nBeneficiario: BENEFICIARIO FICTICIO\nCNPJ do beneficiario: 00000003000125\nPagador: PAGADOR FICTICIO\nCNPJ do pagador: '+self.company.cnpj+'\nVencimento: 22/02/2025\nValor do documento: R$ 123,45\nNumero do documento: PDF-FICTICIO\npago'
        payload=fictional_pdf(text)
        item,created=import_boleto(self.workspace,{'company':self.company},payload)
        self.assertTrue(created)
        self.assertEqual(bytes(item.private_pdf),payload)
        self.assertEqual(item.barcode,CHARGE)
        self.assertEqual(item.amount,Decimal('123.45'))
        self.assertEqual(item.due_on,date(2025,2,22))
        self.assertEqual(item.payer_document,self.company.cnpj)
        self.assertEqual(item.extraction_method,'pdf_text')
        self.assertEqual(item.financial_status,'unknown')
        self.assertTrue(item.needs_review)
        again,new=import_boleto(self.workspace,{'company':self.company},payload)
        self.assertFalse(new);self.assertEqual(item.pk,again.pk)

    def test_pdf_sem_texto_aceito_para_revisao_sem_campos_inventados(self):
        payload=fictional_pdf()
        item,_=import_boleto(self.workspace,{'company':self.company},payload)
        self.assertIsNone(item.barcode);self.assertIsNone(item.amount);self.assertIsNone(item.due_on)
        self.assertEqual(item.extraction_method,'none');self.assertTrue(item.needs_review)
        self.assertIn('OCR não está disponível',item.review_notes)
        _,new=import_boleto(self.workspace,{'company':self.company},payload)
        self.assertFalse(new)

    def test_pdf_multiplo_nao_escolhe_codigo_silenciosamente(self):
        payload=fictional_pdf('FICTICIO\n'+CHARGE+'\n'+COLLECTION10)
        item,_=import_boleto(self.workspace,{'company':self.company},payload)
        self.assertIsNone(item.barcode)
        self.assertIn('múltiplos códigos',item.review_notes)

    def test_revisao_de_nome_preserva_incertezas_originais_da_extracao(self):
        payload=fictional_pdf('FICTICIO\n'+CHARGE+'\n'+COLLECTION10+'\nVencimento: 40/02/2025')
        item,_=import_boleto(self.workspace,{'company':self.company},payload)
        original=item.review_notes
        self.assertIn('múltiplos códigos',original)
        self.assertIn('campo rotulado inválido',original)
        update_boleto(self.workspace,item,{'beneficiary_name':'NOVO NOME FICTICIO'},actor=self.user)
        item.refresh_from_db()
        self.assertIn('múltiplos códigos',item.review_notes)
        self.assertIn('campo rotulado inválido',item.review_notes)
        event=item.events.get(action='revisado')
        self.assertEqual(event.details['review_notes_before'],original)
        self.assertIn('múltiplos códigos',event.details['review_notes_after'])

    def test_pdf_limites_malformado_senha_paginas_tamanho(self):
        for payload in (b'<html/>',b'%PDF-1.4 quebrado',b'%PDF-'+b' '*5*1024*1024,
            fictional_pdf(pages=11),fictional_pdf(password='segredo-ficticio')):
            with self.subTest(size=len(payload)),self.assertRaises(BoletoImportError):
                import_boleto(self.workspace,{'company':self.company},payload)
        self.assertFalse(Boleto.objects.exists())

    def test_pdf_bomba_descompressao_rejeitada_sem_objeto(self):
        payload=fictional_pdf('FICTICIO\n'+'A'*1100000,compressed=True)
        self.assertLess(len(payload),5*1024*1024)
        with self.assertRaises(BoletoImportError): import_boleto(self.workspace,{'company':self.company},payload)

    def test_pdf_nao_aceita_pagador_de_outra_empresa(self):
        payload=fictional_pdf('FICTICIO\n'+CHARGE+'\nCNPJ do pagador: '+self.other_company.cnpj)
        for data in ({'company':self.company},{'company':self.company,'payer_document':self.company.cnpj}):
            with self.assertRaises(BoletoImportError): import_boleto(self.workspace,data,payload)

    def test_pdf_com_codigo_unico_nao_recebe_outro_codigo_manual(self):
        payload=fictional_pdf('FICTICIO\n'+CHARGE)
        with self.assertRaises(BoletoImportError):
            import_boleto(self.workspace,{'company':self.company,'barcode':CHARGE_1001},payload)

    def test_revisao_registra_origem_e_preserva_pdf(self):
        payload=fictional_pdf()
        item,_=import_boleto(self.workspace,{'company':self.company},payload)
        update_boleto(self.workspace,item,{'digitable_line':CHARGE,'amount':'123.45','due_on':'2025-02-22',
            'payer_document':self.company.cnpj},actor=self.user)
        item.refresh_from_db()
        self.assertEqual(item.barcode,CHARGE)
        self.assertEqual(bytes(item.private_pdf),payload)
        self.assertEqual(item.events.filter(action='revisado').count(),1)
        review=item.events.get(action='revisado')
        self.assertIn('Código/linha não identificados',review.details['review_notes_before'])
        self.assertTrue(review.details['review_notes_after'])
        self.assertTrue(any(change['label']=='Código de barras' for change in review.display_changes))
        self.assertEqual(item.financial_status,'unknown')

    def test_revisao_isolada_e_codigo_duplicado_bloqueado(self):
        one,_=import_boleto(self.workspace,self.data)
        two,_=import_boleto(self.workspace,{**self.data,'barcode':CHARGE_1001})
        for data in ({'barcode':CHARGE},{'payer_document':self.other_company.cnpj}):
            with self.assertRaises(BoletoImportError): update_boleto(self.workspace,two,data)
        with self.assertRaises(BoletoImportError): update_boleto(self.other_workspace,one,{'reference':'alheio'})
        with self.assertRaises(BoletoImportError): update_boleto(self.workspace,one,{'reference':'negado'},allowed_companies=[])

    def test_vinculo_explicito_idempotente_sem_nova_obrigacao(self):
        item,_=import_boleto(self.workspace,self.data)
        before=Installment.objects.count()
        item=associate_boleto(self.workspace,item,self.part,actor=self.user)
        associate_boleto(self.workspace,item,self.part)
        self.assertEqual(item.installment_id,self.part.pk)
        self.assertEqual(Installment.objects.count(),before)
        self.assertEqual(item.events.filter(action='associado').count(),1)
        self.part.refresh_from_db();self.assertFalse(self.part.checked)
        self.assertEqual(item.financial_status,'unknown')

    def test_vinculo_nao_cruza_workspace_empresa_ou_escopo(self):
        item,_=import_boleto(self.workspace,self.data)
        other_company=Company.objects.create(workspace=self.workspace,legal_name='OUTRA FICTICIA',cnpj='00000004000170')
        note=Invoice.objects.create(company=other_company,access_key='2'*44,number='OUTRA FICTICIA',series='1',
            issuer_name='FORNECEDOR FICTICIO',issuer_cnpj='00000003000125',issued_on=date(2025,1,1),total='123.45',xml_content='<FICTICIO/>')
        part=Installment.objects.create(invoice=note,number='1',amount='123.45',due_on=date(2025,2,22))
        for workspace,installment,allowed in ((self.other_workspace,self.part,None),(self.workspace,part,None),(self.workspace,self.part,[])):
            with self.assertRaises(BoletoAssociationError): associate_boleto(workspace,item,installment,allowed_companies=allowed)
        item.refresh_from_db();self.assertIsNone(item.installment_id)

    def test_parcela_nao_recebe_segundo_boleto(self):
        one,_=import_boleto(self.workspace,self.data)
        two,_=import_boleto(self.workspace,{**self.data,'barcode':CHARGE_1001})
        associate_boleto(self.workspace,one,self.part)
        with self.assertRaises(BoletoAssociationError): associate_boleto(self.workspace,two,self.part,review_reason='Cessao conferida ficticia')
        self.assertEqual(Boleto.objects.filter(installment=self.part).count(),1)

    def test_divergencia_exige_justificativa_e_guarda_auditoria(self):
        item,_=import_boleto(self.workspace,{**self.data,'amount':'10.00','due_on':'2025-02-23','beneficiary_document':'00000002000180'})
        with self.assertRaises(BoletoAssociationError): associate_boleto(self.workspace,item,self.part)
        item=associate_boleto(self.workspace,item,self.part,review_reason='Cessao de credito e acordo revisados no teste ficticio',source='api')
        event=item.events.get(action='associado')
        self.assertEqual(event.source,'api');self.assertTrue(event.details['warnings'])
        self.assertIn('Cessao',event.details['review_reason'])
        self.assertEqual(item.financial_status,'unknown')

    def test_alteracao_incompativel_com_vinculo_exige_desassociar(self):
        item,_=import_boleto(self.workspace,self.data)
        associate_boleto(self.workspace,item,self.part)
        with self.assertRaises(BoletoImportError): update_boleto(self.workspace,item,{'amount':'10.00'})
        disassociate_boleto(self.workspace,item,actor=self.user)
        update_boleto(self.workspace,item,{'amount':'10.00'})
        item.refresh_from_db();self.assertIsNone(item.installment_id)
        self.assertTrue(Installment.objects.filter(pk=self.part.pk).exists())
        self.assertTrue(item.events.filter(action='desassociado').exists())

    def test_dda_sem_configuracao_nao_simula_sucesso(self):
        connector=UnconfiguredDDAConnector()
        self.assertEqual(connector.status,'configuration_pending')
        with self.assertRaises(DDAConnectorUnavailable): connector.fetch(self.company)


class BoletoAccessTests(TestCase):
    """Testes de HTTP com dados fictícios e sessão proprietária."""
    setUp = BoletoImportTests.setUp
    def test_telas_e_download_privado_escopo(self):
        payload=fictional_pdf('FICTICIO\n'+CHARGE)
        item,_=import_boleto(self.workspace,{'company':self.company},payload)
        self.client.force_login(self.user)
        for name in ('boletos','boleto_import'):
            self.assertEqual(self.client.get(reverse(name)).status_code,200)
        for name in ('boleto_detail','boleto_review','boleto_associate'):
            self.assertEqual(self.client.get(reverse(name,args=[item.pk])).status_code,200)
        response=self.client.get(reverse('boleto_download',args=[item.pk]))
        self.assertEqual(response.content,payload)
        self.assertEqual(response['Cache-Control'],'private, no-store')
        self.assertEqual(response['X-Content-Type-Options'],'nosniff')
        self.assertIn('attachment',response['Content-Disposition'])
        self.client.force_login(self.other)
        for name in ('boleto_detail','boleto_review','boleto_associate','boleto_download'):
            self.assertEqual(self.client.get(reverse(name,args=[item.pk])).status_code,404)
        self.assertEqual(self.client.get(reverse('boletos'),{'company':self.company.pk}).status_code,404)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('boleto_download',args=[item.pk])).status_code,302)

    def test_importacao_revisao_http_e_acoes_post(self):
        self.client.force_login(self.user)
        response=self.client.post(reverse('boleto_import'),{'company':self.company.pk,'digitable_line':CHARGE,
            'payer_document':self.company.cnpj,'amount':'123,45','due_on':'2025-02-22'})
        self.assertEqual(response.status_code,302)
        item=Boleto.objects.get(company=self.company)
        response=self.client.post(reverse('boleto_review',args=[item.pk]),{'digitable_line':CHARGE,
            'payer_document':self.company.cnpj,'amount':'123,45','due_on':'2025-02-22','reference':'FICTICIO REVISADO'})
        self.assertEqual(response.status_code,302)
        item.refresh_from_db();self.assertEqual(item.reference,'FICTICIO REVISADO')
        self.assertEqual(self.client.get(reverse('boleto_disassociate',args=[item.pk])).status_code,405)
        self.assertEqual(self.client.get(reverse('boletos'),{'from':'invalida'}).status_code,400)

    def test_formularios_nao_aceitam_empresa_alheia(self):
        self.client.force_login(self.user)
        response=self.client.post(reverse('boleto_import'),{'company':self.other_company.pk,'digitable_line':CHARGE})
        self.assertEqual(response.status_code,200)
        self.assertFalse(Boleto.objects.exists())
