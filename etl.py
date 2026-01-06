# etl.py
import pandas as pd
import re
from pathlib import Path
import streamlit as st
import locale

@st.cache_data
def carregar_base_vendas(pasta_bases: str) -> pd.DataFrame:
    pasta = Path(pasta_bases)

    # Produtos
    produtos = pd.read_excel(pasta / "Cadastro Produtos.xlsx")

    # Base Vendas (vários arquivos)
    arquivos = sorted(pasta.glob("Base Vendas*.xlsx"))
    dfs = []
    for arq in arquivos:
        df = pd.read_excel(arq)

        m = re.search(r"(20\d{2})", arq.stem)
        if m:
            df["ano"] = int(m.group(1))

        df["arquivo_origem"] = arq.name
        dfs.append(df)

    if not dfs:
        return pd.DataFrame()

    base_vendas = pd.concat(dfs, ignore_index=True)

    # Localidade / Lojas
    localidade = pd.read_excel(pasta / "Cadastro Localidades.xlsx")
    lojas = pd.read_excel(pasta / "Cadastro Lojas.xlsx")
    lojas.columns = lojas.columns.str.strip()
    localidade.columns = localidade.columns.str.strip()

    cols_loc = ["ID Localidade", "País", "Continente"]
    lojas = lojas.merge(
        localidade[cols_loc],
        how="left",
        left_on="id Localidade",
        right_on="ID Localidade",
        validate="many_to_one"
    ).drop(columns=["ID Localidade"])

    # Clientes
    clientes = pd.read_excel(pasta / "Cadastro Clientes.xlsx")
    clientes = clientes.drop(index=0).reset_index(drop=True)
    clientes.columns = clientes.iloc[0]
    clientes = clientes.iloc[1:].reset_index(drop=True)
    clientes = clientes.iloc[:, :-2]

    # Limpeza e junções
    base_vendas = base_vendas.drop(columns=["arquivo_origem"])

    cols_prod = ["SKU", "Produto", "Marca", "Tipo do Produto", "Preço Unitario", "Custo Unitario"]
    base_vendas = base_vendas.merge(produtos[cols_prod], on="SKU", how="left", validate="many_to_one")

    cols_lojas = ["ID Loja", "Nome da Loja", "Quantidade Colaboradores", "Tipo", "País", "Continente"]
    base_vendas = base_vendas.merge(lojas[cols_lojas], on="ID Loja", how="left", validate="many_to_one")

    cols_cli = ["ID Cliente", "Genero", "Estado Civil"]
    base_vendas = base_vendas.merge(clientes[cols_cli], on="ID Cliente", how="left", validate="many_to_one")
    # Faturamento = Preço Unitario x Qtd Vendida
    base_vendas["Faturamento"] = base_vendas["Preço Unitario"] * base_vendas["Qtd Vendida"]
    base_vendas["Genero"] = base_vendas["Genero"].replace({"M": "Masculino", "F": "Feminino"})
    


    ordem = ["Ordem de Compra", "SKU", "Marca", "Produto", "Tipo do Produto", "Qtd Vendida",
             "Preço Unitario", "Custo Unitario","Faturamento", "ID Loja", "Nome da Loja",
             "Quantidade Colaboradores", "Tipo", "País", "Continente",
             "ID Cliente", "Genero", "Estado Civil", "Data da Venda", "ano"]
    base_vendas = base_vendas[ordem]

    return base_vendas
