"""
Embeddings da plataforma: transforma texto em vetor de dimensao fixa.

Troca o TF-IDF do C2.A2 pelo HashingVectorizer: nao precisa de ajuste (fit), devolve sempre
512 numeros e funciona offline. Assim o vetor cabe na coluna `vector(512)` do banco e a
indexacao e a busca ficam consistentes mesmo em processos independentes.

Voce NAO precisa entender a matematica. Precisa saber:
  - vetorizar(texto) devolve uma lista de 512 numeros
  - texto sem nenhuma palavra devolve um vetor zerado (nao serve para comparar)
"""
from sklearn.feature_extraction.text import HashingVectorizer

DIMENSAO = 512


class Vetorizador:

    def __init__(self):
        self._hashing = HashingVectorizer(n_features=DIMENSAO, ngram_range=(1, 2), norm="l2")

    def vetorizar(self, texto: str) -> list[float]:
        return self._hashing.transform([texto]).toarray()[0].tolist()
