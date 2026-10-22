"""Conferência da caixa local, sem afirmar cobertura universal do CNPJ."""
def coverage(stream):
    if stream is None:return {'label':'Não foi possível verificar completamente: ainda não houve consulta nesta fonte.','gaps':[]}
    numbers=sorted(int(n) for n in stream.envelopes.values_list('nsu',flat=True))
    gaps=[]
    previous=0
    for number in numbers:
        if number>previous+1:gaps.append((previous+1,number-1))
        previous=max(previous,number)
    attempted_from_zero=stream.consultations.filter(cursor_sent__in=['0','000000000000000'],http_status=200).exists()
    if stream.last_status=='NENHUM_DOCUMENTO_LOCALIZADO':
        label='Não existem documentos novos nesta fonte a partir do cursor informado.' if numbers else 'Não existem documentos disponíveis nesta fonte nesta consulta.'
    elif stream.last_status in {'DOCUMENTOS_LOCALIZADOS','138'}:label='Documentos recebidos; confira o progresso e as pendências locais.'
    else:label='Não foi possível verificar completamente: consulte a resposta e a configuração deste serviço.'
    return {'label':label,'gaps':gaps[:20],'gap_count':len(gaps),'received':len(numbers),'first':numbers[0] if numbers else None,'last':numbers[-1] if numbers else None,
        'from_zero':attempted_from_zero,'warning':'A sequência local e o fim de um lote não comprovam todo o histórico do CNPJ nem cobertura de outras fontes/municípios.'}
