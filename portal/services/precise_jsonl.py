"""JSONL padrão com datas completas para preservar intervalos e validade."""
from datetime import datetime,time
from django.core.serializers.json import DjangoJSONEncoder
from django.core.serializers.jsonl import Serializer as BaseSerializer,Deserializer


class PreciseEncoder(DjangoJSONEncoder):
    def default(self,value):
        if isinstance(value,datetime):return value.isoformat(timespec='microseconds')
        if isinstance(value,time):
            if value.utcoffset() is not None:raise ValueError('TimeField com timezone não suportado.')
            return value.isoformat(timespec='microseconds')
        return super().default(value)


class Serializer(BaseSerializer):
    def _init_options(self):
        super()._init_options();self.json_kwargs['cls']=PreciseEncoder
