"""Ponto de entrada para execução local do Flask."""

from core.web import criar_app

if __name__ == "__main__":
    criar_app().run(host="127.0.0.1", port=5000)
