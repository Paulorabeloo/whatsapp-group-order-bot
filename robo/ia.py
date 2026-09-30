"""IA de apoio: entra SO quando o motor de regras devolve 'duvida'.

Recebe a mensagem torta ("me separa cinco daquele", "troca o meu pelo maior") + os rateios abertos
e devolve a mesma estrutura que interpretar() devolveria. Se nao tiver certeza, devolve 'duvida' de novo
e o admin e avisado como antes. Sem ANTHROPIC_API_KEY o modulo fica desligado, sem quebrar nada.
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger("ia")

MODELO = os.environ.get("IA_MODELO", "claude-opus-5")

SISTEMA = """Você lê mensagens de um grupo de WhatsApp de venda de decants (frações de perfume) e diz o que a pessoa quis.
Os membros pedem quantidades em ml de um perfume aberto. "APC" é o frasco original completo, tamanho fixo.
Responda só com o JSON pedido. Regras:
- "pedido": a pessoa quer X ml (pode ser mais de um item). Números por extenso valem ("cinco" = 5).
- "apc": quer o frasco completo.
- "alterar": quer mudar a quantidade que já pediu para X ml.
- "cancelar": desistiu.
- "nada": conversa, elogio, pergunta, brincadeira, comentário sobre quanto falta.
- "duvida": tem cara de pedido mas não dá pra ter certeza da quantidade ou da intenção.
Nunca invente quantidade. Em "perfume", copie o nome do rateio aberto a que a pessoa se refere, ou deixe vazio."""

ESQUEMA = {
    "type": "object",
    "properties": {
        "tipo": {"type": "string", "enum": ["pedido", "apc", "alterar", "cancelar", "nada", "duvida"]},
        "ml": {"type": "array", "items": {"type": "integer"}},
        "perfume": {"type": "string"},
        "motivo": {"type": "string"},
    },
    "required": ["tipo", "ml", "perfume", "motivo"],
    "additionalProperties": False,
}


class IA:
    def __init__(self) -> None:
        self.client = None
        if os.environ.get("ANTHROPIC_API_KEY"):
            try:
                import anthropic
                self.client = anthropic.AsyncAnthropic()
            except Exception:  # noqa: BLE001
                log.exception("anthropic nao disponivel")

    @property
    def ligada(self) -> bool:
        return self.client is not None

    async def interpretar(self, texto: str, push_name: str, rateios_abertos: list[str]) -> dict | None:
        """Devolve dict no formato de interpretar() ou None se a IA nao ajudou."""
        if not self.client:
            return None
        import anthropic

        abertos = "\n".join(f"- {n}" for n in rateios_abertos) or "- (nenhum)"
        try:
            resp = await self.client.messages.create(
                model=MODELO,
                max_tokens=256,
                system=SISTEMA,
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": ESQUEMA}},
                messages=[{"role": "user", "content": f"Rateios abertos:\n{abertos}\n\nMensagem de {push_name}:\n{texto}"}],
            )
        except anthropic.RateLimitError:
            log.warning("IA: limite de uso; caiu no admin")
            return None
        except anthropic.APIStatusError as e:
            log.warning("IA: erro %s; caiu no admin", e.status_code)
            return None
        except anthropic.APIConnectionError:
            log.warning("IA: sem rede; caiu no admin")
            return None
        if resp.stop_reason == "refusal":
            return None

        import json
        texto_json = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            d = json.loads(texto_json)
        except json.JSONDecodeError:
            return None

        tipo, ml, perfume = d["tipo"], [int(x) for x in d["ml"] if 0 < int(x) < 200], d.get("perfume", "")
        if tipo == "pedido" and ml:
            return {"tipo": "pedido", "itens": [{"ml": q, "qtd": 1, "dica": perfume} for q in ml], "nome": None, "resto": perfume, "sem_unidade": False, "via_ia": True}
        if tipo == "apc":
            return {"tipo": "apc", "dica": perfume, "nome": None, "via_ia": True}
        if tipo == "alterar" and ml:
            return {"tipo": "alterar", "ml": ml[-1], "dica": perfume, "via_ia": True}
        if tipo == "cancelar":
            return {"tipo": "cancelar", "dica": perfume, "via_ia": True}
        if tipo == "nada":
            return {"tipo": "nada", "via_ia": True}
        return None
