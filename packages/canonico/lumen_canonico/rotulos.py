"""Rótulos públicos do sistema.

Todo texto fixo que aparece para o público vive neste arquivo, e só aqui. O
verificador de vocabulário controlado varre este módulo na integração
contínua (DOC-08, seção 3), então nenhum rótulo com termo que impute conduta
chega a ser publicado.

Os rótulos descrevem a *atividade*, nunca a pessoa ou a empresa (DOC-08,
tabela de vocabulário: "o rótulo recai sobre a atividade, nunca sobre a
pessoa").
"""

ATIVIDADE_PARA_ANALISE = "Atividade para análise"

ROTULO_CONTESTADO = "Atividade para análise — contestação em andamento"
ROTULO_COM_RESPOSTA = "Atividade para análise — com resposta do ente"
ROTULO_RETIFICADO = "Atividade para análise — retificada"
ROTULO_ENCERRADO = "Atividade para análise — análise concluída pelo órgão de controle"
ROTULO_REMOVIDO = "Registro removido — ver nota de remoção"

AVISO_METODOLOGICO = (
    "Este registro é uma sinalização estatística ou processual para análise. "
    "Ele não afirma a ocorrência de ilícito: essa determinação cabe "  # lumen:vocabulario-ok
    "exclusivamente aos órgãos de controle e ao Poder Judiciário."
)
