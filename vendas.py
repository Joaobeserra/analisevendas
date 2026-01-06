import streamlit as st
import pandas as pd
import altair as alt
import re
from pathlib import Path


# ============================================================
# ETL (embutido no mesmo arquivo)
# ============================================================
@st.cache_data
def carregar_base_vendas(pasta_bases: Path) -> pd.DataFrame:
    pasta = Path(pasta_bases)

    # Checagens (para erro amigável no Cloud)
    arq_produtos = pasta / "Cadastro Produtos.xlsx"
    arq_localidades = pasta / "Cadastro Localidades.xlsx"
    arq_lojas = pasta / "Cadastro Lojas.xlsx"
    arq_clientes = pasta / "Cadastro Clientes.xlsx"

    faltando = [p.name for p in [arq_produtos, arq_localidades, arq_lojas, arq_clientes] if not p.exists()]
    if faltando:
        st.error(
            "Arquivos obrigatórios não encontrados na pasta de dados:\n"
            + "\n".join([f"- {x}" for x in faltando])
            + "\n\nDica: crie a pasta `data/` no repositório e suba esses arquivos nela."
        )
        return pd.DataFrame()

    # Produtos
    produtos = pd.read_excel(arq_produtos)

    # Base Vendas (vários arquivos)
    arquivos_vendas = sorted(pasta.glob("Base Vendas*.xlsx"))
    dfs = []
    for arq in arquivos_vendas:
        df_v = pd.read_excel(arq)

        m = re.search(r"(20\d{2})", arq.stem)
        if m:
            df_v["ano"] = int(m.group(1))

        df_v["arquivo_origem"] = arq.name
        dfs.append(df_v)

    if not dfs:
        return pd.DataFrame()

    base_vendas = pd.concat(dfs, ignore_index=True)

    # Localidade / Lojas
    localidade = pd.read_excel(arq_localidades)
    lojas = pd.read_excel(arq_lojas)

    lojas.columns = lojas.columns.str.strip()
    localidade.columns = localidade.columns.str.strip()

    cols_loc = ["ID Localidade", "País", "Continente"]
    lojas = lojas.merge(
        localidade[cols_loc],
        how="left",
        left_on="id Localidade",
        right_on="ID Localidade",
        validate="many_to_one"
    ).drop(columns=["ID Localidade"], errors="ignore")

    # Clientes (tratamento igual ao seu)
    clientes = pd.read_excel(arq_clientes)
    clientes = clientes.drop(index=0, errors="ignore").reset_index(drop=True)
    clientes.columns = clientes.iloc[0]
    clientes = clientes.iloc[1:].reset_index(drop=True)
    clientes = clientes.iloc[:, :-2]

    # Limpeza e junções
    base_vendas = base_vendas.drop(columns=["arquivo_origem"], errors="ignore")

    cols_prod = ["SKU", "Produto", "Marca", "Tipo do Produto", "Preço Unitario", "Custo Unitario"]
    base_vendas = base_vendas.merge(produtos[cols_prod], on="SKU", how="left", validate="many_to_one")

    cols_lojas = ["ID Loja", "Nome da Loja", "Quantidade Colaboradores", "Tipo", "País", "Continente"]
    base_vendas = base_vendas.merge(lojas[cols_lojas], on="ID Loja", how="left", validate="many_to_one")

    cols_cli = ["ID Cliente", "Genero", "Estado Civil"]
    base_vendas = base_vendas.merge(clientes[cols_cli], on="ID Cliente", how="left", validate="many_to_one")

    # Faturamento
    if "Preço Unitario" in base_vendas.columns and "Qtd Vendida" in base_vendas.columns:
        base_vendas["Preço Unitario"] = pd.to_numeric(base_vendas["Preço Unitario"], errors="coerce")
        base_vendas["Qtd Vendida"] = pd.to_numeric(base_vendas["Qtd Vendida"], errors="coerce")
        base_vendas["Faturamento"] = (base_vendas["Preço Unitario"].fillna(0) * base_vendas["Qtd Vendida"].fillna(0))

    # Ajustes de categoria
    if "Genero" in base_vendas.columns:
        base_vendas["Genero"] = base_vendas["Genero"].replace({"M": "Masculino", "F": "Feminino"})

    ordem = [
        "Ordem de Compra", "SKU", "Marca", "Produto", "Tipo do Produto", "Qtd Vendida",
        "Preço Unitario", "Custo Unitario", "Faturamento", "ID Loja", "Nome da Loja",
        "Quantidade Colaboradores", "Tipo", "País", "Continente",
        "ID Cliente", "Genero", "Estado Civil", "Data da Venda", "ano"
    ]
    cols_existentes = [c for c in ordem if c in base_vendas.columns]
    base_vendas = base_vendas[cols_existentes]

    return base_vendas


# ============================================================
# APP
# ============================================================
st.set_page_config(
    page_title="Página Vendas",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.write("# Bem-vindo à Página Vendas")

# Pasta padrão no repo (data/)
ROOT = Path(__file__).resolve().parent  # [web:272]
PASTA_BASES = ROOT / "data"
if not PASTA_BASES.exists():
    PASTA_BASES = ROOT / "Bases"

base_vendas = carregar_base_vendas(PASTA_BASES)

# Se a base vier vazia, evita erro e informa na tela
if base_vendas.empty:
    st.warning("Nenhum arquivo de vendas encontrado ou base vazia.")
    st.stop()

# ---------------------------
# Filtros (barra lateral)
# ---------------------------
with st.sidebar:
    st.header("Filtros")
    periodo = st.selectbox("Período", ["Diário", "Mensal", "Anual"], index=1)

# ---------------------------
# Preparação dos dados
# ---------------------------
base_vendas["Data da Venda"] = pd.to_datetime(base_vendas["Data da Venda"], errors="coerce")
df = base_vendas.dropna(subset=["Data da Venda", "Ordem de Compra"]).copy()

for c in ["Genero", "Estado Civil", "Marca", "Continente"]:
    if c in df.columns:
        df[c] = df[c].fillna("Não informado")

if periodo == "Diário":
    df["periodo"] = df["Data da Venda"].dt.to_period("D").dt.to_timestamp()
elif periodo == "Mensal":
    df["periodo"] = df["Data da Venda"].dt.to_period("M").dt.to_timestamp()
else:  # Anual
    df["periodo"] = df["Data da Venda"].dt.to_period("Y").dt.to_timestamp()

# ---------------------------
# Série de Vendas (base)
# ---------------------------
vendas_periodo = (
    df.groupby("periodo")["Ordem de Compra"]
      .nunique()
      .reset_index(name="valor")
      .sort_values("periodo")
)

# ============================================================
# Seletor de "Análise"
# ============================================================
st.subheader("Análise")

analise = st.selectbox(
    "Escolha a análise",
    ["Venda", "Faturamento", "Média de receita por venda"],
    index=0,
)

# Coluna de faturamento (agora sempre deve existir, porque o ETL cria)
col_fat = "Faturamento" if "Faturamento" in df.columns else None
if col_fat is not None:
    df[col_fat] = pd.to_numeric(df[col_fat], errors="coerce").fillna(0)

serie_venda = vendas_periodo.copy()
serie_venda["tipo"] = "Venda"

if col_fat is not None:
    serie_faturamento = (
        df.groupby("periodo")[col_fat]
          .sum()
          .reset_index(name="valor")
          .sort_values("periodo")
    )
    serie_faturamento["tipo"] = "Faturamento"
else:
    serie_faturamento = pd.DataFrame({"periodo": [], "valor": [], "tipo": []})

if col_fat is not None and not serie_faturamento.empty and not serie_venda.empty:
    tmp = serie_faturamento.merge(
        serie_venda[["periodo", "valor"]].rename(columns={"valor": "vendas"}),
        on="periodo",
        how="left",
    )
    tmp["valor"] = tmp.apply(
        lambda r: (r["valor"] / r["vendas"]) if r.get("vendas", 0) and r["vendas"] > 0 else 0,
        axis=1,
    )
    serie_media = tmp[["periodo", "valor"]].copy()
    serie_media["tipo"] = "Média de receita por venda"
else:
    serie_media = pd.DataFrame({"periodo": [], "valor": [], "tipo": []})

if analise == "Venda":
    serie = serie_venda
    kpi_label = "Vendas (pedidos únicos)"
    kpi_valor = int(df["Ordem de Compra"].nunique())
    kpi_txt = f"{kpi_valor:,}".replace(",", ".")
    y_title = "Vendas"
    tooltip_val = alt.Tooltip("valor:Q", title="Vendas", format=",.0f")
elif analise == "Faturamento":
    if col_fat is None:
        st.warning("Não encontrei a coluna 'Faturamento'.")
        st.stop()
    serie = serie_faturamento
    kpi_label = "Faturamento"
    kpi_valor = float(df[col_fat].sum())
    kpi_txt = f"R$ {kpi_valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    y_title = "Faturamento"
    tooltip_val = alt.Tooltip("valor:Q", title="Faturamento", format=",.2f")
else:
    if col_fat is None:
        st.warning("Não encontrei a coluna 'Faturamento'.")
        st.stop()
    serie = serie_media
    total_vendas = int(df["Ordem de Compra"].nunique())
    total_fat = float(df[col_fat].sum())
    kpi_label = "Média de receita por venda"
    kpi_valor = (total_fat / total_vendas) if total_vendas > 0 else 0.0
    kpi_txt = f"R$ {kpi_valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    y_title = "Média por venda"
    tooltip_val = alt.Tooltip("valor:Q", title="Média por venda", format=",.2f")

METRIC_HEIGHT = 120
st.metric(
    kpi_label,
    kpi_txt,
    delta=None,
    border=True,
    width="stretch",
    height=METRIC_HEIGHT,
)

chart_linha = (
    alt.Chart(serie)
    .mark_line(interpolate="monotone")
    .encode(
        x=alt.X("periodo:T", title="Período"),
        y=alt.Y("valor:Q", title=y_title),
        tooltip=[alt.Tooltip("periodo:T", title="Período"), tooltip_val],
    )
    .properties(height=320)
)

chart_pontos = (
    alt.Chart(serie)
    .mark_circle(size=40)
    .encode(
        x="periodo:T",
        y="valor:Q",
        tooltip=[alt.Tooltip("periodo:T", title="Período"), tooltip_val],
    )
)

st.altair_chart(chart_linha + chart_pontos, use_container_width=True)

st.markdown("---")

# ---------------------------
# Gráficos (50% / 50%)
# ---------------------------
col1, col2 = st.columns(2)

with col1:
    st.subheader("Vendas por Gênero (%)")

    if "Genero" not in df.columns:
        st.warning("Coluna 'Genero' não encontrada na base.")
    else:
        vendas_genero = (
            df.groupby("Genero")["Ordem de Compra"]
              .nunique()
              .reset_index(name="qtd_vendas")
              .sort_values("qtd_vendas", ascending=False)
        )
        total = vendas_genero["qtd_vendas"].sum()
        vendas_genero["pct"] = vendas_genero["qtd_vendas"] / total
        vendas_genero["pct_txt"] = (vendas_genero["pct"] * 100).round(1).astype(str) + "%"

        donut = alt.Chart(vendas_genero).mark_arc(innerRadius=60, outerRadius=100).encode(
            theta=alt.Theta("qtd_vendas:Q"),
            color=alt.Color("Genero:N", legend=alt.Legend(title="Gênero")),
            tooltip=[
                alt.Tooltip("Genero:N", title="Gênero"),
                alt.Tooltip("qtd_vendas:Q", title="Qtd. vendas"),
                alt.Tooltip("pct:Q", title="%", format=".1%")
            ],
        )

        labels = alt.Chart(vendas_genero).mark_text(
            radius=120, size=14, fontWeight="bold"
        ).encode(
            theta=alt.Theta("qtd_vendas:Q", stack=True),
            text=alt.Text("pct_txt:N"),
            color=alt.value("white"),
        )

        st.altair_chart(donut + labels, use_container_width=True)

with col2:
    st.subheader("Vendas por Estado Civil")

    if "Estado Civil" not in df.columns:
        st.warning("Coluna 'Estado Civil' não encontrada na base.")
    else:
        vendas_estado_civil = (
            df.groupby("Estado Civil")["Ordem de Compra"]
              .nunique()
              .reset_index(name="qtd_vendas")
              .sort_values("qtd_vendas", ascending=False)
        )

        bars = alt.Chart(vendas_estado_civil).mark_bar().encode(
            x=alt.X("Estado Civil:N", sort="-y", title="Estado Civil"),
            y=alt.Y("qtd_vendas:Q", title="Qtd. vendas"),
            tooltip=[
                alt.Tooltip("Estado Civil:N", title="Estado Civil"),
                alt.Tooltip("qtd_vendas:Q", title="Qtd. vendas")
            ],
        )

        bar_labels = alt.Chart(vendas_estado_civil).mark_text(dy=-8, size=12).encode(
            x=alt.X("Estado Civil:N", sort="-y"),
            y="qtd_vendas:Q",
            text=alt.Text("qtd_vendas:Q", format=",.0f"),
            color=alt.value("white"),
        )

        st.altair_chart(bars + bar_labels, use_container_width=True)

# ---------------------------
# Barras: Vendas por Marca
# ---------------------------
st.subheader("Quantidade de vendas por marca")

if "Marca" not in df.columns:
    st.warning("Coluna 'Marca' não encontrada na base.")
else:
    vendas_marca = (
        df.groupby("Marca")["Ordem de Compra"]
          .nunique()
          .reset_index(name="qtd_vendas")
          .sort_values("qtd_vendas", ascending=False)
    )

    bars_marca = alt.Chart(vendas_marca).mark_bar().encode(
        x=alt.X("Marca:N", sort="-y", title="Marca", axis=alt.Axis(labelAngle=-45)),
        y=alt.Y("qtd_vendas:Q", title="Quantidade de vendas"),
        tooltip=[
            alt.Tooltip("Marca:N", title="Marca"),
            alt.Tooltip("qtd_vendas:Q", title="Qtd. vendas"),
        ],
    ).properties(height=400)

    labels_marca = alt.Chart(vendas_marca).mark_text(
        dy=-8, size=12, fontWeight="bold"
    ).encode(
        x=alt.X("Marca:N", sort="-y"),
        y="qtd_vendas:Q",
        text=alt.Text("qtd_vendas:Q", format=",.0f"),
        color=alt.value("white"),
    )

    st.altair_chart(bars_marca + labels_marca, use_container_width=True)

# ---------------------------
# Barras: Vendas por Continente
# ---------------------------
st.subheader("Quantidade de vendas por continente")

if "Continente" not in df.columns:
    st.warning("Coluna 'Continente' não encontrada na base.")
else:
    vendas_continente = (
        df.groupby("Continente")["Ordem de Compra"]
          .nunique()
          .reset_index(name="qtd_vendas")
          .sort_values("qtd_vendas", ascending=False)
    )

    bars_cont = alt.Chart(vendas_continente).mark_bar().encode(
        x=alt.X("Continente:N", sort="-y", title="Continente", axis=alt.Axis(labelAngle=0)),
        y=alt.Y("qtd_vendas:Q", title="Quantidade de vendas"),
        tooltip=[
            alt.Tooltip("Continente:N", title="Continente"),
            alt.Tooltip("qtd_vendas:Q", title="Qtd. vendas"),
        ],
    ).properties(height=400)

    labels_cont = alt.Chart(vendas_continente).mark_text(
        dy=-8, size=12, fontWeight="bold"
    ).encode(
        x=alt.X("Continente:N", sort="-y"),
        y="qtd_vendas:Q",
        text=alt.Text("qtd_vendas:Q", format=",.0f"),
        color=alt.value("white"),
    )

    st.altair_chart(bars_cont + labels_cont, use_container_width=True)
