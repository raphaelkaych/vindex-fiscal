"""Evidência local de distribuição: não abre A1, não consulta rede, não grava."""
import json
from collections import Counter
from datetime import timedelta
from django.core.management.base import BaseCommand,CommandError
from django.db.models import Case,When,Value,BooleanField,Count
from portal.models import Company,SefazConsultation,SefazDistributionStream,FiscalStream
from portal.validators import validate_cnpj
from django.core.exceptions import ValidationError


class Command(BaseCommand):
    help='Audita sequência e intervalos persistidos, sem HTTP fiscal ou alteração de NSU.'
    def add_arguments(self,parser):
        parser.add_argument('--cnpj',required=True)
        parser.add_argument('--ambiente',choices=['1','2'],default='1')
    def handle(self,*args,**options):
        try:cnpj=validate_cnpj(options['cnpj'])
        except ValidationError:raise CommandError('CNPJ inválido.') from None
        environment=options['ambiente']
        rows=list(SefazConsultation.objects.filter(state__company__cnpj=cnpj,state__environment=environment,state__source='sefaz').annotate(has_response=Case(When(response_xml='',then=Value(False)),default=Value(True),output_field=BooleanField())).order_by('requested_at','pk').values('id','state__company_id','requested_at','completed_at','official_response_at','requested_nsu','reported_nsu','max_nsu','status','reason','error_code','has_response'))
        previous_cursor=None;previous_wait=None;previous_end=None
        chain=[];early=[];overlap=[]
        for row in rows:
            accepted=row['status'] in {'137','138'}
            if previous_cursor is not None and int(row['requested_nsu'])!=int(previous_cursor):
                chain.append({'attempt':row['id'],'expected_from_local_accepted':previous_cursor,'sent':row['requested_nsu']})
            if previous_wait and row['requested_at']<previous_wait:early.append(row['id'])
            if previous_end and row['requested_at']<previous_end:overlap.append(row['id'])
            if accepted and row['reported_nsu']:previous_cursor=row['reported_nsu']
            reference=max(d for d in [row['completed_at'],row['official_response_at'],row['requested_at']] if d)
            wait_required=row['status'] in {'137','656'} or (accepted and row['reported_nsu']==row['max_nsu'])
            previous_wait=reference+timedelta(hours=1) if wait_required else None
            previous_end=row['completed_at']
        stream=SefazDistributionStream.objects.filter(cnpj=cnpj,environment=environment,source='sefaz').values('last_nsu','reported_nsu','max_nsu','last_status','last_attempt_at','next_attempt_at','lease_until').first()
        evidence={'cnpj':cnpj,'environment':environment,'local_attempt_records':len(rows),'records_with_official_payload':sum(r['has_response'] for r in rows),'status_counts':dict(Counter(r['status'] or 'sem_codigo' for r in rows)),
            'duplicate_company_links':list(Company.objects.filter(cnpj=cnpj).values('id','workspace_id','legal_name','trade_name','deactivated_at','workspace__name','workspace__access_status')),
            'shared_nfe_stream':stream,'other_shared_streams':list(FiscalStream.objects.filter(cnpj=cnpj,environment=environment).values('service','cursor','max_cursor','last_status','next_attempt_at')),
            'local_accepted_chain_differences':chain,'attempts_before_documented_one_hour':early,'overlapping_local_attempt_windows':overlap,
            'last_attempts':rows[-12:],
            'limits':['Registro criado antes do fetch não prova envio/recebimento remoto se não houver resposta.','Sobreposição local inclui processamento; não comprova HTTP simultâneo.','O diagnóstico usa somente evidência persistida; não vê consumidores externos ou respostas perdidas antes de gravar.','NSU aceito/armazenado na fila e entrega privada são etapas distintas. Rejeição não avança o cursor.']}
        self.stdout.write(json.dumps(evidence,ensure_ascii=False,default=str,indent=2))
