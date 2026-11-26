"""
Pagina inicial do ambiente publicado: o navegador do visitante acorda os outros servicos.

No plano gratuito, um servico adormecido nao acordou com as chamadas vindas do gateway;
acordou com o acesso externo. Por isso a pagina abre o /saude de cada um em um quadro e
depois leva a documentacao. Sem endereco publico (compose local) nao ha pagina.
"""
from html import escape

SEGUNDOS = 45

MODELO = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="{segundos};url=/docs">
<title>Plataforma de IA - C3.A2</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 40rem; margin: 3rem auto;
       padding: 0 1rem; line-height: 1.5; }}
iframe {{ width: 100%; height: 4rem; border: 1px solid #ccc; }}
</style>
</head>
<body>
<h1>Plataforma de IA como Serviço</h1>
<p>Acordando os serviços do plano gratuito. Pode levar cerca de um minuto.
A <a href="/docs">documentação da API</a> abre sozinha em {segundos} segundos.</p>
<p>Cada quadro abaixo mostra <code>"status":"ok"</code> quando o serviço está pronto.</p>
{quadros}
</body>
</html>
"""


def montar(urls: tuple[str, ...]) -> str | None:
    """HTML que desperta os enderecos publicos; None se nao houver nenhum."""
    publicos = [escape(f"{url.rstrip('/')}/saude") for url in urls
                if url.startswith("https://")]
    if not publicos:
        return None
    quadros = "\n".join(f'<p>{url}<br><iframe src="{url}" title="{url}"></iframe></p>'
                        for url in publicos)
    return MODELO.format(segundos=SEGUNDOS, quadros=quadros)
