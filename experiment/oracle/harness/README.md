# Oracle harness

Este binário é usado exclusivamente depois que as decisões de controle e PDT
estão seladas. Ele não faz parte da Online Boutique implantada, do staging nem
do `checkout-pdt-controller`.

O processo expõe:

- gRPC `:5051`: doubles determinísticos para carrinho, catálogo, moeda,
  pagamento, frete e e-mail;
- HTTP `:8080/healthz`: saúde do harness;
- HTTP `POST :8080/exercise`: executa um `PlaceOrder` contra a imagem candidata
  e retorna efeitos observados em JSON;
- HTTP `POST :8080/load-order`: executa uma ordem independente e concorrente
  para os perfis não funcionais;
- HTTP `GET|POST :8080/load-config`: consulta ou configura falhas limitadas de
  cauda em pagamento/frete e zera os contadores da janela.

Pagamento e moeda podem operar como proxies para uma dependência candidata.
Moeda também aceita uma dependência de referência separada, permitindo
registrar lado a lado conversões candidatas e conversões esperadas sem usar o
rótulo da mutação como resultado.

Variáveis:

| Nome | Uso |
| --- | --- |
| `CHECKOUT_SERVICE_ADDR` | checkout candidato; padrão `checkoutservice:5050` |
| `CURRENCY_CANDIDATE_ADDR` | serviço de moeda candidato opcional |
| `CURRENCY_REFERENCE_ADDR` | serviço de moeda de referência opcional |
| `PAYMENT_CANDIDATE_ADDR` | serviço de pagamento candidato opcional |
| `GRPC_PORT` | porta dos doubles; padrão `5051` |
| `HTTP_PORT` | porta da API de exercício; padrão `8080` |

Build a partir da raiz do repositório:

```bash
docker build -f experiment/oracle/harness/Dockerfile \
  -t online-boutique/oracle-harness:engineering .
```

O endpoint limita moedas, quantidade de itens, quantidade por item, faults e
timeout à matriz predefinida. As respostas registram ordem dos efeitos,
cobranças, conversões candidata/referência e estado final do carrinho. O
avaliador funcional ainda é responsável por transformar esses fatos nas nove
asserções congeladas da política.
