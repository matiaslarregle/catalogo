import io
import re

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Catálogo Tienda Nube", layout="wide")

st.title("🛍️ Generador de Catálogo para Tienda Nube")

def parse_precio(valor):
    """Convierte '1,550.00', '1.550,00', 1550 o 1550.5 en float."""
    if pd.isna(valor):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    s = re.sub(r"[^\d,.\-]", "", str(valor))
    if not s:
        return None
    if "," in s and "." in s:
        # el último separador es el decimal
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        # "1,550" -> miles | "15,5" -> decimal
        s = s.replace(",", "") if re.search(r",\d{3}$", s) else s.replace(",", ".")
    return pd.to_numeric(s, errors="coerce")


def leer_lista(uploaded_file):
    """Lee la lista de precios (.xls o .xlsx) y devuelve un DataFrame con Codigo, Articulo y Precio."""
    if isinstance(uploaded_file, (str, bytes)) or hasattr(uploaded_file, "__fspath__"):
        with open(uploaded_file, "rb") as f:
            contenido = f.read()
    else:
        contenido = uploaded_file.getvalue()

    # Detecta el formato por el contenido (no por la extensión, que puede venir en mayúsculas)
    if contenido[:4] == b"PK\x03\x04":
        engine = "openpyxl"  # .xlsx
    elif contenido[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        engine = "xlrd"  # .xls
    else:
        raise ValueError("El archivo no parece ser un Excel (.xls o .xlsx).")

    df_raw = pd.read_excel(io.BytesIO(contenido), header=None, engine=engine)

    # Fila de encabezado: la que tiene "Codigo"
    header_row = (
        df_raw.apply(lambda row: row.astype(str).str.contains("Codigo", case=False, na=False))
        .any(axis=1)
        .idxmax()
    )
    columnas = df_raw.iloc[header_row].astype(str).str.strip()
    df_clean = df_raw.iloc[header_row + 1:].copy()
    df_clean.columns = columnas

    df = df_clean[["Codigo", "Articulo", "Precio"]].copy()
    df = df.dropna(how="all").reset_index(drop=True)
    return df


def procesar(uploaded_file):
    df = leer_lista(uploaded_file)

    # Solo se conservan los productos (código numérico); se descartan títulos y subtítulos.
    def codigo_texto(x):
        if pd.isna(x):
            return None
        if isinstance(x, float) and x.is_integer():
            x = int(x)
        return str(x).strip()

    df["Codigo"] = df["Codigo"].apply(codigo_texto)
    df = df[df["Codigo"].apply(lambda x: x is not None and x.isdigit())].reset_index(drop=True)

    df = df.rename(columns={"Codigo": "SKU", "Articulo": "Nombre", "Precio": "Precio"})

    df["Precio"] = df["Precio"].apply(parse_precio)
    df = df.dropna(subset=["Precio"]).reset_index(drop=True)
    df["Nombre"] = df["Nombre"].astype(str).str.strip().replace(r"\s+", " ", regex=True)

    # Filas totalmente repetidas (mismo SKU y mismo precio) se dejan una sola vez
    df = df.drop_duplicates(subset=["SKU", "Precio"]).reset_index(drop=True)
    return df[["SKU", "Nombre", "Precio"]]


uploaded_file = st.file_uploader("Subí la lista de precios (Excel .xls o .xlsx)")

if uploaded_file:
    try:
        df = procesar(uploaded_file)
    except ImportError:
        st.error("Falta instalar xlrd para leer archivos .xls: ejecutá `pip install xlrd`.")
        st.stop()
    except Exception as e:
        st.error(f"No pude leer el archivo: {e}")
        st.stop()

    st.success(f"✅ Datos procesados correctamente ({len(df)} productos)")

    # SKU repetidos con distinto producto/precio: Tienda Nube no sabría a cuál aplicar el precio
    conflictos = df[df["SKU"].duplicated(keep=False)].sort_values("SKU")
    if not conflictos.empty:
        st.warning(
            f"⚠️ Hay {conflictos['SKU'].nunique()} SKU repetidos con productos distintos. "
            "Revisalos antes de subir el archivo:"
        )
        st.dataframe(conflictos)

    precios = df[["SKU", "Precio"]]
    st.dataframe(precios)

    # CSV simple: SKU y Precio
    st.download_button(
        label="📥 Descargar CSV (SKU y Precio)",
        data=precios.to_csv(index=False).encode("utf-8"),
        file_name="precios.csv",
        mime="text/csv"
    )

        file_name="catalogo.csv",
        mime="text/csv"
    )
