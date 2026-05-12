"""
Bot de Controle de Gastos - Telegram + Supabase
Formato: categoria ; valor ; descrição (opcional)
Exemplo: mercado ; 87.50 ; compras da semana
"""

import os
import re
import httpx
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters, CallbackQueryHandler
)

# ──────────────────────────────────────────
# CONFIGURAÇÃO — edite apenas aqui
# ──────────────────────────────────────────

TOKEN          = "8798424595:AAFMfBeoYmSXyBH3vEQ0sq2UPxNSvc0scRU"
SUPABASE_URL   = "https://ahdwgcsqugqwhjgatpea.supabase.co"
SUPABASE_KEY   = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFoZHdnY3NxdWdxd2hqZ2F0cGVhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzg1MzM3NDQsImV4cCI6MjA5NDEwOTc0NH0.-I1_Blm7pX0ehJHGVmLHvyOTGb-f0iEHF8e4Uiesr-Q"

ORCAMENTO = {
    "mercado":     1200.00,
    "restaurante":  600.00,
    "transporte":   400.00,
    "lazer":        300.00,
    "saude":        200.00,
    "moradia":     2500.00,
    "roupas":       300.00,
    "outros":       200.00,
}

ALIASES = {
    "mercado": "mercado", "alimentacao": "mercado", "alimentação": "mercado",
    "supermercado": "mercado", "feira": "mercado", "hortifruti": "mercado",
    "restaurante": "restaurante", "delivery": "restaurante",
    "ifood": "restaurante", "lanche": "restaurante", "almoco": "restaurante",
    "almoço": "restaurante", "jantar": "restaurante",
    "transporte": "transporte", "combustivel": "transporte",
    "combustível": "transporte", "gasolina": "transporte",
    "uber": "transporte", "onibus": "transporte", "ônibus": "transporte",
    "lazer": "lazer", "entretenimento": "lazer", "cinema": "lazer",
    "viagem": "lazer", "passeio": "lazer", "show": "lazer",
    "saude": "saude", "saúde": "saude", "farmacia": "saude",
    "farmácia": "saude", "medico": "saude", "médico": "saude",
    "consulta": "saude", "exame": "saude",
    "moradia": "moradia", "aluguel": "moradia", "contas": "moradia",
    "luz": "moradia", "agua": "moradia", "água": "moradia",
    "internet": "moradia", "condominio": "moradia", "condomínio": "moradia",
    "roupas": "roupas", "roupa": "roupas", "compras": "roupas",
    "calcado": "roupas", "calçado": "roupas", "acessorio": "roupas",
    "outros": "outros", "outro": "outros",
}

# palavras que indicam tentativa de lançamento
PALAVRAS_GATILHO = set(ALIASES.keys()) | {
    "gasto", "gastei", "paguei", "comprei", "uber", "ifood",
    "mercado", "farmacia", "farmácia", "restaurante", "posto",
}

# ──────────────────────────────────────────
# SUPABASE
# ──────────────────────────────────────────

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

def mes_atual():
    return datetime.now().strftime("%Y-%m")

def adicionar_gasto(categoria, valor, descricao, autor):
    data = datetime.now().strftime("%d/%m %H:%M")
    payload = {
        "data": data,
        "mes": mes_atual(),
        "categoria": categoria,
        "valor": valor,
        "descricao": descricao,
        "autor": autor,
    }
    r = httpx.post(f"{SUPABASE_URL}/rest/v1/gastos", headers=HEADERS, json=payload)
    r.raise_for_status()
    return r.json()

def buscar_gastos_mes():
    mes = mes_atual()
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/gastos",
        headers=HEADERS,
        params={"mes": f"eq.{mes}", "order": "criado_em.asc"},
    )
    r.raise_for_status()
    registros = r.json()
    gastos = {cat: [] for cat in ORCAMENTO}
    for reg in registros:
        cat = reg.get("categoria", "")
        if cat in gastos:
            gastos[cat].append({
                "valor": float(reg.get("valor", 0)),
                "autor": reg.get("autor", ""),
                "desc":  reg.get("descricao", ""),
                "data":  reg.get("data", ""),
                "id":    reg.get("id"),
            })
    return gastos

def remover_ultimo():
    mes = mes_atual()
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/gastos",
        headers=HEADERS,
        params={"mes": f"eq.{mes}", "order": "criado_em.desc", "limit": "1"},
    )
    r.raise_for_status()
    registros = r.json()
    if not registros:
        return None
    ultimo = registros[0]
    httpx.delete(
        f"{SUPABASE_URL}/rest/v1/gastos",
        headers=HEADERS,
        params={"id": f"eq.{ultimo['id']}"},
    ).raise_for_status()
    return ultimo

# ──────────────────────────────────────────
# FORMATAÇÃO
# ──────────────────────────────────────────

def barra(gasto, limite, largura=10):
    pct = min(gasto / limite, 1.0) if limite else 0
    cheio = int(pct * largura)
    return "█" * cheio + "░" * (largura - cheio)

def emoji_status(gasto, limite):
    if not limite: return "⚪"
    pct = gasto / limite
    if pct >= 1.0: return "🔴"
    if pct >= 0.80: return "🟡"
    return "🟢"

def formatar_resumo(gastos):
    mes_label = datetime.now().strftime("%B/%Y").capitalize()
    linhas = [f"📊 *Resumo — {mes_label}*\n"]
    total_gasto = 0
    total_orc = sum(ORCAMENTO.values())
    for cat, limite in ORCAMENTO.items():
        regs = gastos.get(cat, [])
        gasto = sum(r["valor"] for r in regs)
        total_gasto += gasto
        saldo = limite - gasto
        b = barra(gasto, limite)
        linhas.append(
            f"{emoji_status(gasto, limite)} *{cat.capitalize()}*\n"
            f"   `{b}` {gasto:.0f}/{limite:.0f}\n"
            f"   Saldo: R$ {saldo:.2f}\n"
        )
    saldo_total = total_orc - total_gasto
    linhas.append(
        f"{'─'*28}\n"
        f"{emoji_status(total_gasto, total_orc)} *TOTAL: R$ {total_gasto:.2f} / {total_orc:.2f}*\n"
        f"Saldo geral: R$ {saldo_total:.2f}"
    )
    return "\n".join(linhas)

MODELO_ERRO = (
    "📌 *Como lançar corretamente:*\n"
    "`categoria ; valor ; descrição`\n\n"
    "*Exemplos:*\n"
    "`mercado ; 87.50 ; compras da semana`\n"
    "`uber ; 22 ; trabalho`\n"
    "`restaurante ; 68 ; jantar aniversário`\n\n"
    "*Categorias aceitas:*\n"
    "`mercado`  `restaurante`  `transporte`\n"
    "`lazer`  `saude`  `moradia`  `roupas`  `outros`"
)

def parece_lancamento(texto):
    """Detecta se a mensagem parece uma tentativa de lançamento mal formatada."""
    texto_lower = texto.lower()
    tem_numero = bool(re.search(r"\d+", texto))
    tem_palavra_gatilho = any(p in texto_lower for p in PALAVRAS_GATILHO)
    tem_separador_errado = any(s in texto for s in [":", "-", "/", "|", ","])
    return tem_numero and (tem_palavra_gatilho or tem_separador_errado)

# ──────────────────────────────────────────
# HANDLERS
# ──────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👋 *Bot de Gastos ativo!*\n\n"
        "*Como registrar:*\n"
        "`categoria ; valor ; descrição`\n\n"
        "*Exemplos:*\n"
        "`mercado ; 95.40 ; semana`\n"
        "`uber ; 22 ; trabalho`\n"
        "`restaurante ; 68 ; jantar aniversário`\n\n"
        "*Categorias:*\n"
        "`mercado`  `restaurante`  `transporte`\n"
        "`lazer`  `saude`  `moradia`  `roupas`  `outros`\n\n"
        "*Comandos:*\n"
        "/resumo — saldo de todas as categorias\n"
        "/historico — últimos 10 lançamentos\n"
        "/orcamento — limites configurados\n"
        "/desfazer — remove o último lançamento\n\n"
        "💾 _Dados salvos no Supabase_"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_resumo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        gastos = buscar_gastos_mes()
        await update.message.reply_text(formatar_resumo(gastos), parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao buscar dados:\n`{e}`", parse_mode="Markdown")

async def cmd_orcamento(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    linhas = ["💰 *Orçamento Mensal*\n"]
    for cat, valor in ORCAMENTO.items():
        linhas.append(f"• *{cat.capitalize()}:* R$ {valor:.2f}")
    linhas.append(f"\n*Total:* R$ {sum(ORCAMENTO.values()):.2f}")
    await update.message.reply_text("\n".join(linhas), parse_mode="Markdown")

async def cmd_historico(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        gastos = buscar_gastos_mes()
        todos = []
        for cat, regs in gastos.items():
            for r in regs:
                todos.append({**r, "categoria": cat})
        if not todos:
            await update.message.reply_text("Nenhum lançamento este mês ainda.")
            return
        ultimos = todos[-10:]
        ultimos.reverse()
        linhas = ["🗂 *Últimos lançamentos*\n"]
        for r in ultimos:
            desc = f" — {r['desc']}" if r.get("desc") else ""
            linhas.append(
                f"`{r['data']}` *{r['categoria'].capitalize()}* "
                f"R$ {r['valor']:.2f}{desc} _{r['autor']}_"
            )
        await update.message.reply_text("\n".join(linhas), parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro:\n`{e}`", parse_mode="Markdown")

async def cmd_desfazer(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        removido = remover_ultimo()
        if not removido:
            await update.message.reply_text("Nenhum lançamento para desfazer.")
            return
        await update.message.reply_text(
            f"↩️ Removido:\n*{removido['categoria'].capitalize()}* — R$ {removido['valor']}"
            + (f" — {removido['descricao']}" if removido.get('descricao') else ""),
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Erro:\n`{e}`", parse_mode="Markdown")

# ──────────────────────────────────────────
# FLUXO DE CONFIRMAÇÃO
# ──────────────────────────────────────────

async def processar_gasto(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()

    # Se não tem ponto e vírgula, verifica se parece tentativa de lançamento
    if ";" not in texto:
        if parece_lancamento(texto):
            await update.message.reply_text(
                f"⚠️ Parece que você tentou registrar um gasto, mas o formato está errado.\n\n{MODELO_ERRO}",
                parse_mode="Markdown"
            )
        return

    partes = texto.split(";")
    if len(partes) < 2:
        await update.message.reply_text(
            f"❌ Formato incorreto.\n\n{MODELO_ERRO}", parse_mode="Markdown"
        )
        return

    cat_raw   = partes[0].strip().lower()
    val_raw   = partes[1].strip().replace(",", ".")
    descricao = partes[2].strip() if len(partes) > 2 else ""

    categoria = ALIASES.get(cat_raw)
    if not categoria:
        await update.message.reply_text(
            f"❌ Categoria *{cat_raw}* não reconhecida.\n\n{MODELO_ERRO}",
            parse_mode="Markdown"
        )
        return

    try:
        valor = float(val_raw)
        if valor <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            f"❌ Valor inválido: *{val_raw}*\n\n{MODELO_ERRO}",
            parse_mode="Markdown"
        )
        return

    autor = update.message.from_user.first_name or "Desconhecido"

    try:
        gastos = buscar_gastos_mes()
        gasto_atual = sum(r["valor"] for r in gastos.get(categoria, []))
    except Exception:
        gasto_atual = 0

    limite     = ORCAMENTO[categoria]
    saldo_apos = limite - gasto_atual - valor
    emoji      = emoji_status(gasto_atual + valor, limite)

    desc_txt = f"\n📝 *Descrição:* {descricao}" if descricao else ""
    alerta = ""
    if saldo_apos < 0:
        alerta = f"\n⚠️ *Isso vai estourar o limite em R$ {abs(saldo_apos):.2f}!*"
    elif limite > 0 and saldo_apos / limite <= 0.20:
        alerta = f"\n⚠️ Após este lançamento restam R$ {saldo_apos:.2f} nesta categoria."

    msg_confirmacao = (
        f"📋 *Confirmar lançamento?*\n\n"
        f"👤 *Quem:* {autor}\n"
        f"🏷 *Categoria:* {categoria.capitalize()}\n"
        f"💰 *Valor:* R$ {valor:.2f}"
        f"{desc_txt}\n\n"
        f"{emoji} Saldo após: R$ {saldo_apos:.2f} de R$ {limite:.2f}"
        f"{alerta}"
    )

    pending_key = f"pending_{update.message.from_user.id}"
    ctx.bot_data[pending_key] = {
        "categoria": categoria,
        "valor":     valor,
        "descricao": descricao,
        "autor":     autor,
    }

    teclado = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Confirmar", callback_data=f"confirm:{pending_key}"),
        InlineKeyboardButton("❌ Cancelar",  callback_data=f"cancel:{pending_key}"),
    ]])

    await update.message.reply_text(msg_confirmacao, parse_mode="Markdown", reply_markup=teclado)


async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    acao, pending_key = query.data.split(":", 1)
    dados = ctx.bot_data.pop(pending_key, None)

    if not dados:
        await query.edit_message_text("⚠️ Lançamento expirado. Envie novamente.")
        return

    if acao == "cancel":
        await query.edit_message_text("❌ *Lançamento cancelado.*", parse_mode="Markdown")
        return

    try:
        adicionar_gasto(dados["categoria"], dados["valor"], dados["descricao"], dados["autor"])

        gastos    = buscar_gastos_mes()
        gasto_cat = sum(r["valor"] for r in gastos.get(dados["categoria"], []))
        limite    = ORCAMENTO[dados["categoria"]]
        saldo     = limite - gasto_cat
        emoji     = emoji_status(gasto_cat, limite)

        desc_txt = f" — _{dados['descricao']}_" if dados["descricao"] else ""
        alerta = ""
        if gasto_cat > limite:
            alerta = f"\n⚠️ *Limite estourado em R$ {abs(saldo):.2f}!*"
        elif limite > 0 and saldo / limite <= 0.20:
            alerta = f"\n⚠️ Restam apenas R$ {saldo:.2f} nesta categoria."

        await query.edit_message_text(
            f"✅ *{dados['categoria'].capitalize()}* +R$ {dados['valor']:.2f}{desc_txt}\n"
            f"{emoji} Saldo: R$ {saldo:.2f} de R$ {limite:.2f}{alerta}",
            parse_mode="Markdown"
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Erro ao salvar:\n`{e}`", parse_mode="Markdown")

# ──────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("resumo",    cmd_resumo))
    app.add_handler(CommandHandler("orcamento", cmd_orcamento))
    app.add_handler(CommandHandler("historico", cmd_historico))
    app.add_handler(CommandHandler("desfazer",  cmd_desfazer))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, processar_gasto))
    print("Bot rodando v3...")
    app.run_polling()

if __name__ == "__main__":
    main()
