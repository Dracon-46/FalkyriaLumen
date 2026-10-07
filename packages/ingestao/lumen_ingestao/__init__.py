"""Ingestão do Lumen: coleta das fontes públicas e preservação da prova na camada bronze.

``portas`` define a porta ``FonteDados`` e o laço de coleta; ``coleta_http`` e
``cliente_http`` fazem as requisições segundo a política de coleta responsável;
``bronze``, ``armazem_s3`` e ``s3`` guardam cada resposta, datada e endereçada pelo
hash; ``adaptadores`` implementa a porta para cada família de fonte.
"""
