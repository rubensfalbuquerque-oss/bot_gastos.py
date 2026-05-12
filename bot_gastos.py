"""
Bot de Controle de Gastos - Telegram + Supabase
Formato: categoria ; valor ; descrição (opcional)
Exemplo: mercado ; 87.50 ; compras da semana
"""

import os
import re
import httpx
from datetime import datetime
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters, CallbackQueryHandler, ConversationHandler
)

# ──────────────────────────────────────────
# CONFIGURAÇÃO — edite apenas aqui
# ──────────────────────────────────────────


def fmt_brl(valor):
    """Formata valor em reais com vírgula: R$ 1.200,00"""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

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

PALAVRAS_GATILHO = set(ALIASES.keys()) | {
    "gasto", "gastei", "paguei", "comprei", "uber", "ifood",
    "mercado", "farmacia", "farmácia", "restaurante", "posto",
}

# estados para ConversationHandler
AGUARDA_NOVA_CATEGORIA, AGUARDA_NOVO_VALOR, AGUARDA_NOME_CAT, AGUARDA_LIMITE_CAT = range(4)

# ──────────────────────────────────────────
# SUPABASE
# ──────────────────────────────────────────

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

BR_TZ = pytz.timezone("America/Sao_Paulo")

def agora_br():
    return datetime.now(BR_TZ)

def mes_atual():
    return agora_br().strftime("%Y-%m")

def data_hora():
    return agora_br().strftime("%d/%m/%Y")

def adicionar_gasto(categoria, valor, descricao, autor):
    payload = {
        "data": data_hora(),
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


def buscar_todos_mes():
    """Retorna lista flat de todos os registros do mês com id."""
    mes = mes_atual()
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/gastos",
        headers=HEADERS,
        params={"mes": f"eq.{mes}", "order": "criado_em.desc"},
    )
    r.raise_for_status()
    return r.json()

def deletar_por_id(id_registro):
    httpx.delete(
        f"{SUPABASE_URL}/rest/v1/gastos",
        headers=HEADERS,
        params={"id": f"eq.{id_registro}"},
    ).raise_for_status()


def buscar_recorrentes():
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/recorrentes",
        headers=HEADERS,
        params={"order": "dia.asc"},
    )
    r.raise_for_status()
    return r.json()

def salvar_recorrente(categoria, valor, descricao, dia):
    payload = {
        "categoria": categoria,
        "valor": valor,
        "descricao": descricao,
        "dia": int(dia),
    }
    r = httpx.post(f"{SUPABASE_URL}/rest/v1/recorrentes", headers=HEADERS, json=payload)
    r.raise_for_status()

# ──────────────────────────────────────────
# FORMATAÇÃO
# ──────────────────────────────────────────

def barra(gasto, limite, largura=10):
    pct = min(gasto / limite, 1.0) if limite else 0
    cheio = int(pct * largura)
    vazio = largura - cheio
    return "▓" * cheio + "░" * vazio

def emoji_status(gasto, limite):
    if not limite: return "⚪"
    pct = gasto / limite
    if pct >= 1.0: return "🔴"
    if pct >= 0.80: return "🟡"
    return "🟢"

def formatar_resumo(gastos):
    hoje = agora_br().strftime("%d/%m/%Y")
    linhas = [f"📊 *Resumo — {hoje}*\n"]
    total_gasto = 0
    total_orc = sum(ORCAMENTO.values())
    for cat, limite in ORCAMENTO.items():
        regs = gastos.get(cat, [])
        gasto = sum(r["valor"] for r in regs)
        total_gasto += gasto
        saldo = limite - gasto
        b = barra(gasto, limite)
        pct_cat = (gasto / limite * 100) if limite else 0
        linhas.append(
            f"{emoji_status(gasto, limite)} *{cat.capitalize()}* — {fmt_brl(gasto)}/{fmt_brl(limite)} ({pct_cat:.0f}%)\n"
            f"   `{b}`\n"
            f"   Saldo: {fmt_brl(saldo)}\n"
        )
    saldo_total = total_orc - total_gasto
    pct_usado = (total_gasto / total_orc * 100) if total_orc else 0
    pct_saldo = 100 - pct_usado
    linhas.append(
        f"{'─'*28}\n"
        f"{emoji_status(total_gasto, total_orc)} *TOTAL: {fmt_brl(total_gasto)} / {fmt_brl(total_orc)}* ({pct_usado:.0f}% usado)\n"
        f"Saldo geral: {fmt_brl(saldo_total)} ({pct_saldo:.0f}% restante)"
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
    texto_lower = texto.lower()
    tem_numero = bool(re.search(r"\d+", texto))
    tem_palavra_gatilho = any(p in texto_lower for p in PALAVRAS_GATILHO)
    tem_separador_errado = any(s in texto for s in [":", "-", "/", "|", ","])
    return tem_numero and (tem_palavra_gatilho or tem_separador_errado)

# ──────────────────────────────────────────
# HANDLERS — CONSULTAS
# ──────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    hoje = agora_br().strftime("%d/%m/%Y")
    msg = (
        f"👋 *Bot de Gastos ativo!* — {hoje}\n\n"
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
        "/painel — painel clicável com todas as funções\n"
        "/resumo — saldo de todas as categorias\n"
        "/meusgastos — resumo por usuário\n"
        "/historico — lista completa de gastos do mês\n"
        "/orcamento — limites configurados\n"
        "/nova\\_categoria — criar uma nova categoria\n"
        "/alterar\\_categoria — renomear uma categoria\n"
        "/alterar\\_valor — mudar o limite de uma categoria\n"
        "/deletar — escolher e deletar qualquer lançamento\n"
        "/recorrentes — ver lançamentos recorrentes\n"
        "/desfazer — remove o último lançamento\n\n"
        "💾 _Dados salvos no Supabase_"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")



async def enviar_painel(update_or_message, ctx):
    """Envia o painel após qualquer comando de consulta."""
    hoje = agora_br().strftime("%d/%m/%Y %H:%M")
    teclado = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Resumo",        callback_data="painel:resumo"),
            InlineKeyboardButton("📋 Histórico",      callback_data="painel:historico"),
        ],
        [
            InlineKeyboardButton("👤 Meus Gastos",    callback_data="painel:meusgastos"),
            InlineKeyboardButton("💰 Orçamento",      callback_data="painel:orcamento"),
        ],
        [
            InlineKeyboardButton("🔁 Recorrentes",    callback_data="painel:recorrentes"),
            InlineKeyboardButton("🗑 Deletar",        callback_data="painel:deletar"),
        ],
        [
            InlineKeyboardButton("➕ Nova Categoria",  callback_data="painel:nova_categoria"),
            InlineKeyboardButton("✏️ Renomear Cat.",  callback_data="painel:alterar_categoria"),
        ],
        [
            InlineKeyboardButton("💲 Alterar Limite", callback_data="painel:alterar_valor"),
            InlineKeyboardButton("↩️ Desfazer",       callback_data="painel:desfazer"),
        ],
    ])
    msg = update_or_message if hasattr(update_or_message, 'reply_text') else update_or_message.message
    await msg.reply_text(
        f"🎛 *Painel* — _{hoje}_\nEscolha uma opção:",
        parse_mode="Markdown",
        reply_markup=teclado
    )

async def cmd_painel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    hoje = agora_br().strftime("%d/%m/%Y %H:%M")
    teclado = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Resumo",        callback_data="painel:resumo"),
            InlineKeyboardButton("📋 Histórico",      callback_data="painel:historico"),
        ],
        [
            InlineKeyboardButton("👤 Meus Gastos",    callback_data="painel:meusgastos"),
            InlineKeyboardButton("💰 Orçamento",      callback_data="painel:orcamento"),
        ],
        [
            InlineKeyboardButton("💰 Orçamento",      callback_data="painel:orcamento"),
            InlineKeyboardButton("🔁 Recorrentes",    callback_data="painel:recorrentes"),
        ],
        [
            InlineKeyboardButton("➕ Nova Categoria",  callback_data="painel:nova_categoria"),
            InlineKeyboardButton("✏️ Renomear Cat.",  callback_data="painel:alterar_categoria"),
        ],
        [
            InlineKeyboardButton("💲 Alterar Limite", callback_data="painel:alterar_valor"),
            InlineKeyboardButton("🗑 Deletar",        callback_data="painel:deletar"),
        ],
        [
            InlineKeyboardButton("↩️ Desfazer último", callback_data="painel:desfazer"),
        ],
    ])
    await update.message.reply_text(
        f"🎛 *Painel de Controle*\n_{hoje}_\n\nEscolha uma opção:",
        parse_mode="Markdown",
        reply_markup=teclado
    )

async def cmd_resumo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        gastos = buscar_gastos_mes()
        await update.message.reply_text(formatar_resumo(gastos), parse_mode="Markdown")
        await enviar_painel(update.message, ctx)
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao buscar dados:\n`{e}`", parse_mode="Markdown")

async def cmd_orcamento(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    hoje = agora_br().strftime("%d/%m/%Y")
    linhas = [f"💰 *Orçamento Mensal — {hoje}*\n"]
    for cat, valor in ORCAMENTO.items():
        linhas.append(f"• *{cat.capitalize()}:* {fmt_brl(valor)}")
    linhas.append(f"\n*Total:* {fmt_brl(sum(ORCAMENTO.values()))}")
    await update.message.reply_text("\n".join(linhas), parse_mode="Markdown")
    await enviar_painel(update.message, ctx)

async def cmd_historico_old(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
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
        hoje = agora_br().strftime("%d/%m/%Y")
        linhas = [f"🗂 *Últimos lançamentos — {hoje}*\n"]
        for r in ultimos:
            desc = f" — {r['desc']}" if r.get("desc") else ""
            # data já vem no formato "dd/mm/yyyy hh:mm"
            desc_txt = r['desc'] if r.get('desc') else "—"
            linhas.append(
                f"`{r['data']}` | *{r['categoria'].capitalize()}* | "
                f"{fmt_brl(r['valor'])} | {desc_txt} | _{r['autor']}_"
            )
        await update.message.reply_text("\n".join(linhas), parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro:\n`{e}`", parse_mode="Markdown")

async def cmd_historico(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        gastos = buscar_gastos_mes()
        hoje = agora_br().strftime("%d/%m/%Y")

        todos = []
        for cat, regs in gastos.items():
            for r in regs:
                todos.append({**r, "categoria": cat})

        if not todos:
            await update.message.reply_text("Nenhum lançamento este mês ainda.")
            return

        linhas = [f"📋 *Tabela de gastos — {hoje}*\n"]

        for cat, limite in ORCAMENTO.items():
            regs = gastos.get(cat, [])
            if not regs:
                continue
            total_cat = sum(r["valor"] for r in regs)
            linhas.append(f"\n*{cat.capitalize()}* — Total: {fmt_brl(total_cat)}")
            linhas.append("─" * 20)
            for r in regs:
                partes_data = r['data'].split(" ") if r.get('data') else ["?", "?"]
                dt = partes_data[0] if len(partes_data) > 0 else "?"
                hr = partes_data[1] if len(partes_data) > 1 else "?"
                desc_txt = r['desc'] if r.get('desc') else "—"
                linhas.append(f"`{dt}` | `{hr}` | {fmt_brl(r['valor'])} | {desc_txt} | _{r['autor']}_")

        total_geral = sum(r["valor"] for r in todos)
        linhas.append(f"\n{'─' * 20}")
        linhas.append(f"💰 *Total gasto: {fmt_brl(total_geral)}*")

        await update.message.reply_text("\n".join(linhas), parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro:\n`{e}`", parse_mode="Markdown")

async def cmd_meusgastos(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        gastos = buscar_gastos_mes()
        hoje = agora_br().strftime("%d/%m/%Y")

        # agrupa por autor
        por_autor = {}
        for cat, regs in gastos.items():
            for r in regs:
                autor = r["autor"]
                if autor not in por_autor:
                    por_autor[autor] = {"total": 0, "cats": {}}
                por_autor[autor]["total"] += r["valor"]
                por_autor[autor]["cats"][cat] = por_autor[autor]["cats"].get(cat, 0) + r["valor"]

        if not por_autor:
            await update.message.reply_text("Nenhum lançamento este mês ainda.")
            return

        total_geral = sum(r["valor"] for regs in gastos.values() for r in regs)
        linhas = [f"👤 *Gastos por usuário — {hoje}*\n"]

        for autor, info in sorted(por_autor.items()):
            pct = info["total"] / total_geral * 100 if total_geral else 0
            linhas.append(f"*{autor}* — {fmt_brl(info['total'])} ({pct:.0f}% do total)")
            for cat, val in sorted(info["cats"].items(), key=lambda x: -x[1]):
                pct_cat = val / info["total"] * 100 if info["total"] else 0
                linhas.append(f"   • {cat.capitalize()}: {fmt_brl(val)} ({pct_cat:.0f}%)")
            linhas.append("")

        linhas.append(f"{'─'*20}")
        linhas.append(f"💰 *Total geral: {fmt_brl(total_geral)}*")

        await update.message.reply_text("\n".join(linhas), parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro:\n`{e}`", parse_mode="Markdown")


async def cmd_deletar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        registros = buscar_todos_mes()
        if not registros:
            await update.message.reply_text("Nenhum lançamento este mês para deletar.")
            return

        # monta botões — máximo 20 para não estourar o Telegram
        botoes = []
        for i, reg in enumerate(registros[:20], start=1):
            cat   = reg.get("categoria", "?").capitalize()
            val   = float(reg.get("valor", 0))
            desc  = reg.get("descricao", "")
            data  = reg.get("data", "")
            autor = reg.get("autor", "")
            partes_data = data.split(" ") if data else ["?", "?"]
            dt = partes_data[0] if len(partes_data) > 0 else "?"
            hr = partes_data[1] if len(partes_data) > 1 else "?"
            desc_txt = desc if desc else "—"
            label = f"#{i} {dt} | {hr} | {cat} | {fmt_brl(val)} | {desc_txt} | {autor}"
            botoes.append([InlineKeyboardButton(label, callback_data=f"del:{reg['id']}")])

        botoes.append([InlineKeyboardButton("❌ Cancelar", callback_data="del:cancelar")])
        teclado = InlineKeyboardMarkup(botoes)

        await update.message.reply_text(
            "🗑 *Selecione o lançamento para deletar:*",
            parse_mode="Markdown",
            reply_markup=teclado
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Erro:\n`{e}`", parse_mode="Markdown")


async def cmd_recorrentes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        registros = buscar_recorrentes()
        if not registros:
            await update.message.reply_text("Nenhum lançamento recorrente cadastrado.")
            return
        hoje = agora_br().strftime("%d/%m/%Y")
        linhas = [f"🔁 *Lançamentos recorrentes — {hoje}*\n"]
        for r in registros:
            cat  = r.get("categoria", "?").capitalize()
            val  = float(r.get("valor", 0))
            desc = r.get("descricao", "")
            dia  = r.get("dia", "?")
            linha = f"• Todo dia *{dia}* — {cat} {fmt_brl(val)}"
            if desc:
                linha += f" — {desc}"
            linhas.append(linha)
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
            f"↩️ Removido:\n*{removido['categoria'].capitalize()}* — {fmt_brl(float(removido['valor']))}"
            + (f" — {removido['descricao']}" if removido.get('descricao') else ""),
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Erro:\n`{e}`", parse_mode="Markdown")


# ──────────────────────────────────────────
# CRIAR NOVA CATEGORIA
# ──────────────────────────────────────────

async def cmd_nova_categoria(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "➕ *Nova categoria*\n\nDigite o nome da nova categoria:",
        parse_mode="Markdown"
    )
    return AGUARDA_NOME_CAT

async def receber_nome_nova_cat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    nome = update.message.text.strip().lower()

    if nome in ORCAMENTO:
        await update.message.reply_text(
            f"❌ Já existe uma categoria chamada *{nome.capitalize()}*. Use outro nome.",
            parse_mode="Markdown"
        )
        return AGUARDA_NOME_CAT

    ctx.user_data["nova_cat_nome"] = nome
    await update.message.reply_text(
        f"💰 Categoria: *{nome.capitalize()}*\n\nAgora digite o limite mensal em R$:",
        parse_mode="Markdown"
    )
    return AGUARDA_LIMITE_CAT

async def receber_limite_nova_cat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val_raw = update.message.text.strip().replace(",", ".")
    nome = ctx.user_data.get("nova_cat_nome")

    if not nome:
        await update.message.reply_text("❌ Operação expirada. Use /nova_categoria novamente.")
        return ConversationHandler.END

    try:
        limite = float(val_raw)
        if limite <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Valor inválido. Digite um número positivo.")
        return AGUARDA_LIMITE_CAT

    # pede confirmação com botões
    ctx.user_data["nova_cat_limite"] = limite
    teclado = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Confirmar", callback_data=f"novacat:confirmar"),
        InlineKeyboardButton("❌ Cancelar",  callback_data=f"novacat:cancelar"),
    ]])
    await update.message.reply_text(
        f"📋 *Confirmar nova categoria?*\n\n"
        f"🏷 *Nome:* {nome.capitalize()}\n"
        f"💰 *Limite mensal:* {fmt_brl(limite)}",
        parse_mode="Markdown",
        reply_markup=teclado
    )
    return ConversationHandler.END

# ──────────────────────────────────────────
# ALTERAR CATEGORIA — conversa em etapas
# ──────────────────────────────────────────

async def cmd_alterar_categoria(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cats = list(ORCAMENTO.keys())
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton(c.capitalize(), callback_data=f"altcat:{c}")]
        for c in cats
    ])
    await update.message.reply_text(
        "✏️ *Qual categoria quer renomear?*",
        parse_mode="Markdown",
        reply_markup=teclado
    )

async def cb_alterar_categoria(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat = query.data.split(":")[1]
    ctx.user_data["cat_renomear"] = cat
    await query.edit_message_text(
        f"✏️ Renomeando *{cat.capitalize()}*.\n\nDigite o novo nome:",
        parse_mode="Markdown"
    )
    return AGUARDA_NOVA_CATEGORIA

async def receber_nova_categoria(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    novo_nome = update.message.text.strip().lower()
    cat_antiga = ctx.user_data.get("cat_renomear")

    if not cat_antiga or cat_antiga not in ORCAMENTO:
        await update.message.reply_text("❌ Operação expirada. Use /alterar_categoria novamente.")
        return ConversationHandler.END

    if novo_nome in ORCAMENTO and novo_nome != cat_antiga:
        await update.message.reply_text(f"❌ Já existe uma categoria chamada *{novo_nome}*.", parse_mode="Markdown")
        return ConversationHandler.END

    # renomeia no dicionário
    valor = ORCAMENTO.pop(cat_antiga)
    ORCAMENTO[novo_nome] = valor

    # atualiza aliases
    for alias, cat in list(ALIASES.items()):
        if cat == cat_antiga:
            ALIASES[alias] = novo_nome
    ALIASES[novo_nome] = novo_nome

    await update.message.reply_text(
        f"✅ Categoria *{cat_antiga.capitalize()}* renomeada para *{novo_nome.capitalize()}*!",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# ──────────────────────────────────────────
# ALTERAR VALOR — conversa em etapas
# ──────────────────────────────────────────

async def cmd_alterar_valor(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cats = list(ORCAMENTO.keys())
    teclado = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{c.capitalize()} — {fmt_brl(ORCAMENTO[c])}", callback_data=f"altval:{c}")]
        for c in cats
    ])
    await update.message.reply_text(
        "💰 *Qual categoria quer alterar o limite?*",
        parse_mode="Markdown",
        reply_markup=teclado
    )

async def cb_alterar_valor(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat = query.data.split(":")[1]
    ctx.user_data["cat_valor"] = cat
    await query.edit_message_text(
        f"💰 Limite atual de *{cat.capitalize()}*: {fmt_brl(ORCAMENTO[cat])}\n\nDigite o novo valor:",
        parse_mode="Markdown"
    )
    return AGUARDA_NOVO_VALOR

async def receber_novo_valor(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cat = ctx.user_data.get("cat_valor")
    val_raw = update.message.text.strip().replace(",", ".")

    if not cat or cat not in ORCAMENTO:
        await update.message.reply_text("❌ Operação expirada. Use /alterar_valor novamente.")
        return ConversationHandler.END

    try:
        novo_valor = float(val_raw)
        if novo_valor <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Valor inválido. Digite um número positivo.")
        return ConversationHandler.END

    antigo = ORCAMENTO[cat]
    ORCAMENTO[cat] = novo_valor

    await update.message.reply_text(
        f"✅ Limite de *{cat.capitalize()}* alterado de {fmt_brl(antigo)} para {fmt_brl(novo_valor)}!",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def cancelar_conversa(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operação cancelada.")
    return ConversationHandler.END

# ──────────────────────────────────────────
# FLUXO DE CONFIRMAÇÃO DE GASTO
# ──────────────────────────────────────────

ATALHOS = {
    "painel":             cmd_painel,
    "resumo":             cmd_resumo,
    "tabela":             cmd_historico,
    "historico":          cmd_historico,
    "histórico":          cmd_historico,
    "tabela":             cmd_historico,
    "orcamento":          cmd_orcamento,
    "orçamento":          cmd_orcamento,
    "meusgastos":         cmd_meusgastos,
    "meus gastos":        cmd_meusgastos,
    "recorrentes":        cmd_recorrentes,
    "desfazer":           cmd_desfazer,
    "deletar":            cmd_deletar,
    "nova categoria":     cmd_nova_categoria,
    "alterar categoria":  cmd_alterar_categoria,
    "alterar valor":      cmd_alterar_valor,
}

async def processar_gasto(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()

    # verifica atalhos por palavra-chave
    texto_lower = texto.lower()
    for palavra, handler in ATALHOS.items():
        if texto_lower == palavra:
            await handler(update, ctx)
            return

    if ";" not in texto:
        if parece_lancamento(texto):
            await update.message.reply_text(
                f"⚠️ Parece que você tentou registrar um gasto, mas o formato está errado.\n\n{MODELO_ERRO}",
                parse_mode="Markdown"
            )
        return

    partes = texto.split(";")
    if len(partes) < 2:
        await update.message.reply_text(f"❌ Formato incorreto.\n\n{MODELO_ERRO}", parse_mode="Markdown")
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
        await update.message.reply_text(f"❌ Valor inválido: *{val_raw}*\n\n{MODELO_ERRO}", parse_mode="Markdown")
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
        alerta = f"\n⚠️ *Isso vai estourar o limite em {fmt_brl(abs(saldo_apos))}!*"
    elif limite > 0 and saldo_apos / limite <= 0.20:
        alerta = f"\n⚠️ Após este lançamento restam {fmt_brl(saldo_apos)} nesta categoria."

    msg_confirmacao = (
        f"📋 *Confirmar lançamento?*\n\n"
        f"📅 *Data:* {data_hora()}\n"
        f"👤 *Quem:* {autor}\n"
        f"🏷 *Categoria:* {categoria.capitalize()}\n"
        f"💰 *Valor:* {fmt_brl(valor)}"
        f"{desc_txt}\n\n"
        f"{emoji} Saldo após: {fmt_brl(saldo_apos)} de {fmt_brl(limite)}"
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

    # callbacks de alterar categoria/valor são tratados pelo ConversationHandler
    if query.data.startswith("painel:"):
        acao = query.data.split(":")[1]
        await query.answer()

        # para ações que abrem conversa, avisa o usuário para usar o comando
        if acao in ("nova_categoria", "alterar_categoria", "alterar_valor"):
            cmds = {
                "nova_categoria":    "/nova\\_categoria",
                "alterar_categoria": "/alterar\\_categoria",
                "alterar_valor":     "/alterar\\_valor",
            }
            await query.edit_message_text(
                f"Use o comando {cmds[acao]} para continuar.",
                parse_mode="Markdown"
            )
            return

        # ações diretas — chama o handler correspondente simulando update
        if acao == "resumo":
            try:
                gastos = buscar_gastos_mes()
                await query.edit_message_text(formatar_resumo(gastos), parse_mode="Markdown")
            except Exception as e:
                await query.edit_message_text(f"❌ Erro:\n`{e}`", parse_mode="Markdown")

        elif acao == "UNUSED_historico_bloco":
            try:
                gastos = buscar_gastos_mes()
                hoje = agora_br().strftime("%d/%m/%Y")
                todos = [
                    {**r, "categoria": cat}
                    for cat, regs in gastos.items()
                    for r in regs
                ]
                if not todos:
                    await query.edit_message_text("Nenhum lançamento este mês ainda.")
                    return
                linhas = [f"📋 *Tabela de gastos — {hoje}*\n"]
                for cat, limite in ORCAMENTO.items():
                    regs = gastos.get(cat, [])
                    if not regs:
                        continue
                    total_cat = sum(r["valor"] for r in regs)
                    linhas.append(f"\n*{cat.capitalize()}* — Total: {fmt_brl(total_cat)}")
                    linhas.append("─" * 20)
                    for r in regs:
                        partes_data = r["data"].split(" ") if r.get("data") else ["?","?"]
                        dt = partes_data[0] if len(partes_data)>0 else "?"
                        hr = partes_data[1] if len(partes_data)>1 else "?"
                        desc_txt = r["desc"] if r.get("desc") else "—"
                        linhas.append(f"`{dt}` | `{hr}` | {fmt_brl(r['valor'])} | {desc_txt} | _{r['autor']}_")
                total_geral = sum(r["valor"] for r in todos)
                linhas.append(f"\n{'─'*20}")
                linhas.append(f"💰 *Total gasto: {fmt_brl(total_geral)}*")
                await query.edit_message_text("\n".join(linhas), parse_mode="Markdown")
            except Exception as e:
                await query.edit_message_text(f"❌ Erro:\n`{e}`", parse_mode="Markdown")

        elif acao == "meusgastos":
            try:
                gastos = buscar_gastos_mes()
                hoje = agora_br().strftime("%d/%m/%Y")
                por_autor = {}
                for cat, regs in gastos.items():
                    for r in regs:
                        autor = r["autor"]
                        if autor not in por_autor:
                            por_autor[autor] = {"total": 0, "cats": {}}
                        por_autor[autor]["total"] += r["valor"]
                        por_autor[autor]["cats"][cat] = por_autor[autor]["cats"].get(cat, 0) + r["valor"]
                if not por_autor:
                    await query.edit_message_text("Nenhum lançamento este mês ainda.")
                    return
                total_geral = sum(r["valor"] for regs in gastos.values() for r in regs)
                linhas = [f"👤 *Gastos por usuário — {hoje}*\n"]
                for autor, info in sorted(por_autor.items()):
                    pct = info["total"] / total_geral * 100 if total_geral else 0
                    linhas.append(f"*{autor}* — {fmt_brl(info['total'])} ({pct:.0f}% do total)")
                    for cat, val in sorted(info["cats"].items(), key=lambda x: -x[1]):
                        pct_cat = val / info["total"] * 100 if info["total"] else 0
                        linhas.append(f"   • {cat.capitalize()}: {fmt_brl(val)} ({pct_cat:.0f}%)")
                    linhas.append("")
                linhas.append(f"{'─'*20}")
                linhas.append(f"💰 *Total geral: {fmt_brl(total_geral)}*")
                await query.edit_message_text("\n".join(linhas), parse_mode="Markdown")
            except Exception as e:
                await query.edit_message_text(f"❌ Erro:\n`{e}`", parse_mode="Markdown")

        elif acao == "historico":
            try:
                gastos = buscar_gastos_mes()
                todos = []
                for cat, regs in gastos.items():
                    for r in regs:
                        todos.append({**r, "categoria": cat})
                if not todos:
                    await query.edit_message_text("Nenhum lançamento este mês ainda.")
                    return
                hoje = agora_br().strftime("%d/%m/%Y")
                ultimos = todos[-10:]
                ultimos.reverse()
                linhas = [f"🗂 *Últimos lançamentos — {hoje}*\n"]
                for r in ultimos:
                    desc_txt = r["desc"] if r.get("desc") else "—"
                    linhas.append(f"`{r['data']}` | *{r['categoria'].capitalize()}* | {fmt_brl(r['valor'])} | {desc_txt} | _{r['autor']}_")
                await query.edit_message_text("\n".join(linhas), parse_mode="Markdown")
            except Exception as e:
                await query.edit_message_text(f"❌ Erro:\n`{e}`", parse_mode="Markdown")

        elif acao == "orcamento":
            hoje = agora_br().strftime("%d/%m/%Y")
            linhas = [f"💰 *Orçamento Mensal — {hoje}*\n"]
            for cat, valor in ORCAMENTO.items():
                linhas.append(f"• *{cat.capitalize()}:* {fmt_brl(valor)}")
            linhas.append(f"\n*Total:* {fmt_brl(sum(ORCAMENTO.values()))}")
            await query.edit_message_text("\n".join(linhas), parse_mode="Markdown")

        elif acao == "recorrentes":
            try:
                registros = buscar_recorrentes()
                if not registros:
                    await query.edit_message_text("Nenhum lançamento recorrente cadastrado.")
                    return
                hoje = agora_br().strftime("%d/%m/%Y")
                linhas = [f"🔁 *Lançamentos recorrentes — {hoje}*\n"]
                for r in registros:
                    cat  = r.get("categoria","?").capitalize()
                    val  = float(r.get("valor",0))
                    desc = r.get("descricao","")
                    dia  = r.get("dia","?")
                    linha = f"• Todo dia *{dia}* — {cat} {fmt_brl(val)}"
                    if desc:
                        linha += f" — {desc}"
                    linhas.append(linha)
                await query.edit_message_text("\n".join(linhas), parse_mode="Markdown")
            except Exception as e:
                await query.edit_message_text(f"❌ Erro:\n`{e}`", parse_mode="Markdown")

        elif acao == "deletar":
            try:
                registros = buscar_todos_mes()
                if not registros:
                    await query.edit_message_text("Nenhum lançamento este mês para deletar.")
                    return
                botoes = []
                for i, reg in enumerate(registros[:20], start=1):
                    cat   = reg.get("categoria","?").capitalize()
                    val   = float(reg.get("valor",0))
                    desc  = reg.get("descricao","")
                    data  = reg.get("data","")
                    autor = reg.get("autor","")
                    desc_txt = desc if desc else "—"
                    label = f"#{i} {data} | {cat} | {fmt_brl(val)} | {desc_txt} | {autor}"
                    botoes.append([InlineKeyboardButton(label, callback_data=f"del:{reg['id']}")])
                botoes.append([InlineKeyboardButton("❌ Cancelar", callback_data="del:cancelar")])
                await query.edit_message_text(
                    "🗑 *Selecione o lançamento para deletar:*",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(botoes)
                )
            except Exception as e:
                await query.edit_message_text(f"❌ Erro:\n`{e}`", parse_mode="Markdown")

        elif acao == "desfazer":
            try:
                removido = remover_ultimo()
                if not removido:
                    await query.edit_message_text("Nenhum lançamento para desfazer.")
                    return
                await query.edit_message_text(
                    f"↩️ Removido:\n*{removido['categoria'].capitalize()}* — {fmt_brl(float(removido['valor']))}"
                    + (f" — {removido['descricao']}" if removido.get('descricao') else ""),
                    parse_mode="Markdown"
                )
            except Exception as e:
                await query.edit_message_text(f"❌ Erro:\n`{e}`", parse_mode="Markdown")
        return

    if query.data.startswith("rec:"):
        partes = query.data.split(":")
        acao = partes[1]
        if acao == "nao":
            await query.edit_message_text("👍 Ok, lançamento avulso registrado.")
            return
        # rec:sim:categoria:valor:descricao:dia
        _, _, cat, val, desc, dia = partes
        try:
            salvar_recorrente(cat, float(val), desc, dia)
            await query.edit_message_text(
                f"🔁 *Recorrente salvo!*\n"
                f"Todo dia *{dia}* será lembrado: {cat.capitalize()} {fmt_brl(float(val))}"
                + (f" — {desc}" if desc else ""),
                parse_mode="Markdown"
            )
        except Exception as e:
            await query.edit_message_text(f"❌ Erro ao salvar recorrente:\n`{e}`", parse_mode="Markdown")
        return

    if query.data.startswith("novacat:"):
        acao = query.data.split(":")[1]
        if acao == "cancelar":
            await query.edit_message_text("❌ *Criação de categoria cancelada.*", parse_mode="Markdown")
            return
        nome  = query.from_user and ctx.user_data.get("nova_cat_nome")
        limite = ctx.user_data.get("nova_cat_limite")
        if not nome or not limite:
            await query.edit_message_text("⚠️ Dados expirados. Use /nova_categoria novamente.")
            return
        ORCAMENTO[nome] = limite
        ALIASES[nome] = nome
        await query.edit_message_text(
            f"✅ Categoria *{nome.capitalize()}* criada com limite de {fmt_brl(limite)}!\n\n"
            f"Já pode lançar usando:\n`{nome} ; valor ; descrição`",
            parse_mode="Markdown"
        )
        return

    if query.data.startswith("del:"):
        id_reg = query.data.split(":", 1)[1]
        if id_reg == "cancelar":
            await query.edit_message_text("Operação cancelada.")
            return
        try:
            deletar_por_id(int(id_reg))
            await query.edit_message_text("🗑 *Lançamento deletado com sucesso!*", parse_mode="Markdown")
        except Exception as e:
            await query.edit_message_text(f"❌ Erro ao deletar:\n`{e}`", parse_mode="Markdown")
        return

    if query.data.startswith("altcat:") or query.data.startswith("altval:"):
        if query.data.startswith("altcat:"):
            return await cb_alterar_categoria(update, ctx)
        else:
            return await cb_alterar_valor(update, ctx)

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
            alerta = f"\n⚠️ *Limite estourado em {fmt_brl(abs(saldo))}!*"
        elif limite > 0 and saldo / limite <= 0.20:
            alerta = f"\n⚠️ Restam apenas {fmt_brl(saldo)} nesta categoria."

        await query.edit_message_text(
            f"✅ *{dados['categoria'].capitalize()}* +{fmt_brl(dados['valor'])}{desc_txt}\n"
            f"{emoji} Saldo: {fmt_brl(saldo)} de {fmt_brl(limite)}{alerta}",
            parse_mode="Markdown"
        )
        # envia resumo completo logo após confirmação
        await query.message.reply_text(formatar_resumo(gastos), parse_mode="Markdown")

        # pergunta se é recorrente
        dia = agora_br().strftime("%d")
        teclado_rec = InlineKeyboardMarkup([[
            InlineKeyboardButton(f"✅ Sim, todo dia {dia}", callback_data=f"rec:sim:{dados['categoria']}:{dados['valor']}:{dados['descricao']}:{dia}"),
            InlineKeyboardButton("❌ Não", callback_data="rec:nao"),
        ]])
        await query.message.reply_text(
            f"🔁 *Este lançamento se repete todo dia {dia} do mês?*",
            parse_mode="Markdown",
            reply_markup=teclado_rec
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Erro ao salvar:\n`{e}`", parse_mode="Markdown")

# ──────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv_nova_categoria = ConversationHandler(
        entry_points=[CommandHandler("nova_categoria", cmd_nova_categoria)],
        states={
            AGUARDA_NOME_CAT:   [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_nome_nova_cat)],
            AGUARDA_LIMITE_CAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_limite_nova_cat)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar_conversa)],
    )

    conv_categoria = ConversationHandler(
        entry_points=[CommandHandler("alterar_categoria", cmd_alterar_categoria)],
        states={
            AGUARDA_NOVA_CATEGORIA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_nova_categoria)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar_conversa)],
    )

    conv_valor = ConversationHandler(
        entry_points=[CommandHandler("alterar_valor", cmd_alterar_valor)],
        states={
            AGUARDA_NOVO_VALOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_novo_valor)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar_conversa)],
    )

    app.add_handler(CommandHandler("start",      cmd_start))
    app.add_handler(CommandHandler("painel",     cmd_painel))
    app.add_handler(CommandHandler("resumo",     cmd_resumo))
    app.add_handler(CommandHandler("orcamento",  cmd_orcamento))
    app.add_handler(CommandHandler("historico",  cmd_historico))
    app.add_handler(CommandHandler("meusgastos", cmd_meusgastos))
    app.add_handler(CommandHandler("deletar",    cmd_deletar))
    app.add_handler(CommandHandler("recorrentes", cmd_recorrentes))
    app.add_handler(CommandHandler("desfazer",   cmd_desfazer))
    app.add_handler(conv_nova_categoria)
    app.add_handler(conv_categoria)
    app.add_handler(conv_valor)
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, processar_gasto))

    print("Bot rodando v17...")
    app.run_polling()

if __name__ == "__main__":
    main()
