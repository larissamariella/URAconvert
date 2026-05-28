# Conversor de Audio para URA

Aplicacao web para converter um ou varios audios para WAV mono, 8 kHz, codec CCITT u-Law (`pcm_mulaw`), formato usado em URA telefonica.

## Requisitos

- Python 3.10+
- ffmpeg instalado e disponivel no `PATH`

## Rodar localmente

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --reload
```

Acesse `http://127.0.0.1:8000`.

## Hospedagem

Instale as dependencias de Python e o `ffmpeg` no servidor. O comando de inicializacao pode ser:

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

Os arquivos convertidos ficam em `storage/jobs/`. Em producao, use uma rotina periodica para limpar jobs antigos conforme a sua politica de retencao.

## Rodar com Docker

O `Dockerfile` ja instala o `ffmpeg`.

```bash
docker build -t ura-convert .
docker run --rm -p 8000:8000 ura-convert
```

Teste de saude:

```bash
curl http://127.0.0.1:8000/api/health
```
