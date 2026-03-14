import pandas as pd
import streamlit as st

st.set_page_config(page_title="Catálogo Tienda Nube", layout="wide")

st.title("🛍️ Generador de Catálogo para Tienda Nube")

uploaded_file = st.file_uploader("Subí el archivo Excel", type=["xlsx"])

if uploaded_file:
    df_raw = pd.read_excel(uploaded_file, header=None)
    header_row = df_raw.apply(lambda row: row.astype(str).str.contains("Codigo", case=False, na=False)).any(axis=1).idxmax()
    df_clean = pd.read_excel(uploaded_file, skiprows=header_row)

    df = df_clean[["Codigo ", "Articulo", "Precio"]]
    df = df.dropna(how="all").reset_index(drop=True)

    df["Es_Categoría"] = df["Codigo "].apply(lambda x: not str(x).isdigit())
    df.loc[df["Es_Categoría"], "Categoría"] = df["Codigo "]
    df["Categoría"] = df["Categoría"].ffill()

    df = df[~df["Es_Categoría"]].drop(columns=["Es_Categoría"]).reset_index(drop=True)

    categorias_a_borrar = [
        "CÁSCARA MORENA FRACCIONAD", "PASAS DE UVA", "PRODUCTOS DE PANADERÍA", "DESDE EL CAMPO",
        "LA ESQUINA DE LAS FLORES", "FRUTAS DEL SUR", "LUPE SIN TACC", "PASTAS DOÑA ROSA", "RISKY - DIT",
        "SABORES SIN TAC", "ABUELA MECHA PRODUCTOS AR", "AJI NO MOTO", "D Y D PANIFICADOS",
        "FIDEOS PAESE DEI SAPORI", "FINCA CAVE CANEM", "ACEITES ACETOS SALSAS DELICATESSEN",
        "ACEITES DE SEMILLA", "EL ALMACEN ORGANICO", "OLIVA X 330G", "REINO DE LEON", "FELICES LAS VACAS",
        "MIEL JALEA REAL POLEN Y P", "CREMAS DE ORDEÑE", "EL ATLETA NATURAL", "ROYAL PREMIUN LINE",
        "YARA / ORIGEN", "YERBA BUENOS AIRES", "ESPECIES Y SEMILLAS", "SUPLEMENTOS"
    ]

    df.loc[df["Categoría"].isin(categorias_a_borrar), "Categoría"] = None
    df["Categoría"] = df["Categoría"].ffill()

    df = df.rename(columns={
        "Codigo ": "SKU",
        "Articulo": "Nombre",
        "Precio": "Precio",
        "Categoría": "Categorías"
    })

    df['Categorías'] = df['Categorías'].replace({
        'INFUSIONES, YERBA MATE, SUPLEMENTOS': 'INFUSIONES YERBA MATE Y SUPLEMENTOS',
        'ALIMENTO PARA CELIACOS': 'ALIMENTOS PARA CELIACOS'
    })

    df["Nombre"] = df["Nombre"].str.strip().replace(r'\s+', ' ', regex=True)

    df["Identificador de URL"] = (
        df["Nombre"]
        .str.lower()
        .str.replace(r'[^a-z0-9\s-]', '', regex=True)
        .str.replace(r'\s+', '-', regex=True)
    )

    df = df.replace({
        "º": "ro", "&": "and", "`": "'", "´": "'", "N°": "Nro", "%": "porciento"
    }, regex=True)

    df = df.drop(columns=["Categorías"])

    st.success("✅ Datos procesados correctamente")
    st.dataframe(df)

    # Descargar CSV
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Descargar catálogo en CSV",
        data=csv,
        file_name="catalogo.csv",
        mime="text/csv"
    )
