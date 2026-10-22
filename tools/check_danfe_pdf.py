"""Renderiza somente XMLs fictícios. Não lê documentos de clientes nem faz rede."""
import os
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.chdir(ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')


def main():
    import django
    django.setup()
    try:
        import pypdfium2 as pdfium
    except ImportError:
        raise SystemExit('Instale as dependências de conferência: .\\.venv\\Scripts\\python.exe -m pip install -r requirements-dev.txt') from None
    from defusedxml import ElementTree
    from portal.test_danfe import complete_synthetic_xml,NS
    from portal.services.danfe import generate_danfe
    folder=ROOT/'tmp'/'pdfs'
    folder.mkdir(parents=True,exist_ok=True)
    for orientation,label,items in [('1','retrato',90),('2','paisagem',12)]:
        payload=complete_synthetic_xml('00000001000136',items=items,orientation=orientation)
        key=ElementTree.fromstring(payload).find('n:NFe/n:infNFe',NS).get('Id')[3:]
        note=SimpleNamespace(xml_content=payload.decode(),access_key=key,number='1001',
            company=SimpleNamespace(cnpj='00000001000136'),is_demo=True)
        data=generate_danfe(note)
        if orientation=='1':(folder/'danfe-ficticio-qa.pdf').write_bytes(data)
        pdf=pdfium.PdfDocument(data)
        for index in range(len(pdf)):
            page=pdf[index]
            bitmap=page.render(scale=2)
            bitmap.to_pil().save(folder/f'danfe-ficticio-final-{label}-{index+1:02}.png')
            bitmap.close();page.close()
        print(f'Conferência fictícia {label}: {len(pdf)} página(s), imagens em tmp/pdfs/.')
        pdf.close()


if __name__=='__main__':main()
