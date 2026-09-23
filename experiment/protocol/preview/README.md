# Prévia do corpus cego

`public-corpus.json` demonstra o formato que a CI/CD, o staging e o PDT poderão
ler. Ele contém apenas IDs opacos, ordem, repetições, blocos e o compromisso
criptográfico do manifesto reservado.

Esta prévia foi gerada enquanto o protocolo estava em
`pre-registration-candidate`; portanto, registra
`confirmatory_eligible: false` e não pode ser usada na coleta principal. A
chave e o manifesto correspondentes ficam em `.private-preview/`, que é
ignorado pelo Git e tem permissão somente para o usuário local.

O protocolo continuou evoluindo depois dessa geração. Logo, o hash preservado
nesta prévia é deliberadamente histórico e já não coincide com o arquivo
`protocol-v1.json` atual. Ela serve somente como teste de formato; não deve ser
regenerada ou reinterpretada como corpus válido. O corpus confirmatório terá
uma chave, IDs e compromisso novos depois do congelamento.

O gerador recusa protocolos não congelados por padrão. `--allow-draft` existe
somente para validar esta prévia:

```bash
python3 experiment/scripts/manage-blinded-corpus.py generate \
  --protocol experiment/protocol/protocol-v1.json \
  --key experiment/protocol/.private-preview/blinding-key.bin \
  --public-output experiment/protocol/preview/public-corpus.json \
  --oracle-output experiment/protocol/.private-preview/oracle-manifest.json \
  --allow-draft
```

Na geração definitiva será criada uma nova chave; nenhum ID desta prévia será
reutilizado.
