
import io
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Actualizador de precios Tiendanube",
    layout="wide"
)

st.title("🛍️ Actualizador de precios Tiendanube")

st.write(
    "Subí la lista de precios XLS y el catálogo exportado "
    "de Tiendanube. Solo se actualizarán los precios de "
    "los productos que ya existen en tu tienda."
)


# ==========================================
# FUNCIONES
# ==========================================

def sku_normalizado(valor):
    if pd.isna(valor):
        return ""

    s = str(valor).strip()

    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]

    return s


def precio_decimal(valor):
    if pd.isna(valor) or str(valor).strip() == "":
        return None

    s = re.sub(r"[^\d,.\-]", "", str(valor).strip())

    if not s:
        return None

    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")

    elif "," in s:
        if re.search(r",\d{3}$", s):
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")

    try:
        p = Decimal(s)

        if p.is_finite() and p >= 0:
            return p

        return None

    except InvalidOperation:
        return None


def leer_xls(archivo):
    contenido = archivo.getvalue()

    if contenido.startswith(b"PK\x03\x04"):
        engine = "openpyxl"

    elif contenido.startswith(
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    ):
        engine = "xlrd"

    else:
        raise ValueError("El archivo debe ser XLS o XLSX.")

    raw = pd.read_excel(
        io.BytesIO(contenido),
        header=None,
        engine=engine,
        dtype=str,
        keep_default_na=False
    )

    # Buscar encabezado Codigo
    filas = raw.apply(
        lambda row: row.astype(str)
        .str.strip()
        .str.fullmatch(r"(?i)c[oó]digo")
        .any(),
        axis=1
    )

    if not filas.any():
        raise ValueError("No se encontró la columna Codigo.")

    indice = filas[filas].index[0]

    columnas = (
        raw.iloc[indice]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    raw = raw.iloc[indice + 1:].copy()
    raw.columns = columnas

    codigo = next(
        (c for c in raw.columns if c in ["codigo", "código"]),
        None
    )

    precio = next(
        (c for c in raw.columns if c == "precio"),
        None
    )

    articulo = next(
        (c for c in raw.columns if c in ["articulo", "artículo"]),
        None
    )

    if not codigo or not precio:
        raise ValueError(
            "La lista debe contener Codigo y Precio."
        )

    lista = pd.DataFrame({
        "SKU": raw[codigo].map(sku_normalizado),
        "Precio_nuevo": raw[precio].map(precio_decimal)
    })

    if articulo:
        lista["Articulo"] = raw[articulo].astype(str).str.strip()
    else:
        lista["Articulo"] = ""

    lista = lista[
        lista["SKU"].str.fullmatch(r"\d+")
    ].copy()

    return lista.reset_index(drop=True)


def leer_tiendanube(archivo):
    contenido = archivo.getvalue()

    for encoding in ["utf-8-sig", "cp1252"]:
        try:
            texto = contenido.decode(encoding)
            break
        except UnicodeDecodeError:
            continue

    primera_linea = texto.splitlines()[0]

    separador = (
        ";" if primera_linea.count(";") > primera_linea.count(",")
        else ","
    )

    df = pd.read_csv(
        io.StringIO(texto),
        dtype=str,
        keep_default_na=False,
        sep=separador
    )

    necesarias = {"SKU", "Precio", "Identificador de URL"}

    if not necesarias.issubset(df.columns):
        raise ValueError(
            "El CSV debe contener SKU, Precio "
            "e Identificador de URL."
        )

    return df, separador, encoding


# ==========================================
# CARGA DE ARCHIVOS
# ==========================================

xls = st.file_uploader(
    "1. Subí la lista de precios (XLS/XLSX)",
    type=["xls", "xlsx"]
)

tienda = st.file_uploader(
    "2. Subí el catálogo exportado de Tiendanube (CSV)",
    type=["csv"]
)

st.info(
    "Los SKU se comparan exactamente. "
    "Por ejemplo, 00489 y 489 son códigos diferentes."
)


# ==========================================
# PROCESAMIENTO
# ==========================================

if xls is not None and tienda is not None:

    try:
        lista = leer_xls(xls)
        catalogo, separador, encoding = leer_tiendanube(tienda)

        original = catalogo.copy(deep=True)

        # Comparación exacta de códigos
        lista["_clave"] = lista["SKU"]
        catalogo["_clave"] = catalogo["SKU"].map(
            sku_normalizado
        )

        # ==================================
        # DETECTAR SKU DUPLICADOS
        # ==================================

        duplicados = lista[
            lista["_clave"].duplicated(keep=False)
        ].copy()

        cantidad_duplicados = duplicados["_clave"].nunique()

        lista_valida = lista[
            lista["Precio_nuevo"].notna()
        ].copy()

        lista_valida["_precio_final"] = (
            lista_valida["Precio_nuevo"].map(
                lambda p: p.quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP
                )
            )
        )

        # Mismo SKU con precios diferentes
        cantidad_precios = (
            lista_valida.groupby("_clave")["_precio_final"]
            .nunique()
        )

        codigos_conflictivos = set(
            cantidad_precios[cantidad_precios > 1].index
        )

        conflictos_xls = lista_valida[
            lista_valida["_clave"].isin(codigos_conflictivos)
        ].copy()

        # SKU repetidos en Tiendanube
        conflictos_tienda = catalogo[
            catalogo["_clave"].ne("")
            & catalogo["_clave"].duplicated(keep=False)
        ].copy()

        bloqueados = (
            codigos_conflictivos
            | set(conflictos_tienda["_clave"])
        )

        # Repetidos idénticos se usan una sola vez
        lista_ok = (
            lista_valida[
                ~lista_valida["_clave"].isin(bloqueados)
            ]
            .drop_duplicates("_clave")
        )

        mapa_precios = dict(
            zip(
                lista_ok["_clave"],
                lista_ok["_precio_final"]
            )
        )

        # ==================================
        # ACTUALIZAR SOLO PRECIOS
        # ==================================

        catalogo["Precio_anterior"] = catalogo["Precio"]

        catalogo["Precio_nuevo"] = (
            catalogo["_clave"].map(mapa_precios)
        )

        coincide = catalogo["Precio_nuevo"].notna()

        catalogo.loc[coincide, "Precio"] = (
            catalogo.loc[coincide, "Precio_nuevo"]
            .map(lambda p: format(p, ".2f"))
        )

        anterior = catalogo["Precio_anterior"].map(
            precio_decimal
        )

        nuevo = catalogo["Precio"].map(
            precio_decimal
        )

        cambios = catalogo[
            coincide & (anterior != nuevo)
        ].copy()

        # ==================================
        # RESUMEN
        # ==================================

        total = len(original)
        encontrados = int(coincide.sum())
        modificados = len(cambios)
        sin_cambios = encontrados - modificados

        st.divider()
        st.subheader("📊 Resumen de actualización")

        st.success(
            f"Se detectaron {total} productos/variantes "
            f"en Tiendanube. Se encontraron {encontrados} "
            f"coincidencias con la lista de precios y "
            f"{modificados} cambiaron de precio."
        )

        c1, c2, c3, c4 = st.columns(4)

        c1.metric("Productos en Tiendanube", total)
        c2.metric("Coincidencias con XLS", encontrados)
        c3.metric("Precios modificados", modificados)
        c4.metric("Coinciden sin cambios", sin_cambios)

        # ==================================
        # ALERTA DE DUPLICADOS
        # ==================================

        st.divider()
        st.subheader("⚠️ Control de SKU duplicados")

        if cantidad_duplicados > 0:

            st.warning(
                f"Se detectaron {cantidad_duplicados} "
                "SKU duplicados en la lista de precios."
            )

            with st.expander("Ver SKU duplicados"):

                st.dataframe(
                    duplicados[
                        ["SKU", "Articulo", "Precio_nuevo"]
                    ].sort_values("SKU"),
                    use_container_width=True,
                    hide_index=True
                )

        else:
            st.success("No se detectaron SKU duplicados.")

        # ==================================
        # TABLA DE CAMBIOS DE PRECIOS
        # ==================================

        st.divider()
        st.subheader("💰 Estos son los precios que cambiaron")

        columnas = ["SKU"]

        if "Nombre" in cambios.columns:
            columnas.append("Nombre")

        resumen = cambios[columnas].copy()

        resumen["Precio anterior"] = (
            cambios["Precio_anterior"]
            .map(precio_decimal)
            .to_numpy()
        )

        resumen["Precio nuevo"] = (
            cambios["Precio"]
            .map(precio_decimal)
            .to_numpy()
        )

        resumen["Diferencia ($)"] = resumen.apply(
            lambda fila: (
                fila["Precio nuevo"] - fila["Precio anterior"]
            )
            if (
                fila["Precio anterior"] is not None
                and fila["Precio nuevo"] is not None
            )
            else None,
            axis=1
        )

        resumen["Cambio (%)"] = resumen.apply(
            lambda fila: round(
                float(
                    100 * fila["Diferencia ($)"]
                    / fila["Precio anterior"]
                ),
                2
            )
            if (
                fila["Diferencia ($)"] is not None
                and fila["Precio anterior"]
                not in (None, Decimal("0"))
            )
            else None,
            axis=1
        )

        resumen["Movimiento"] = (
            resumen["Diferencia ($)"].map(
                lambda valor:
                "⬆ Aumentó"
                if valor is not None and valor > 0
                else (
                    "⬇ Bajó"
                    if valor is not None and valor < 0
                    else "Sin comparación"
                )
            )
        )

        if resumen.empty:
            st.info("No se encontraron cambios de precios.")

        else:
            st.dataframe(
                resumen,
                use_container_width=True,
                hide_index=True
            )

            st.download_button(
                "📥 Descargar informe de cambios",
                data=resumen.to_csv(
                    index=False
                ).encode("utf-8-sig"),
                file_name="informe_cambios_precios.csv",
                mime="text/csv"
            )

        # ==================================
        # CONFLICTOS
        # ==================================

        if (
            not conflictos_xls.empty
            or not conflictos_tienda.empty
        ):

            with st.expander(
                "⚠️ Códigos con conflictos",
                expanded=True
            ):

                if not conflictos_xls.empty:
                    st.warning(
                        "Hay SKU con precios diferentes "
                        "en el XLS. No se actualizaron."
                    )

                    st.dataframe(
                        conflictos_xls[
                            ["SKU", "Articulo", "Precio_nuevo"]
                        ],
                        hide_index=True
                    )

                if not conflictos_tienda.empty:
                    st.warning(
                        "Hay SKU repetidos en Tiendanube. "
                        "No se actualizaron."
                    )

                    st.dataframe(
                        conflictos_tienda[
                            [
                                c for c in [
                                    "SKU", "Nombre",
                                    "Identificador de URL", "Precio"
                                ]
                                if c in conflictos_tienda.columns
                            ]
                        ],
                        hide_index=True
                    )

        # ==================================
        # PRODUCTOS QUE NO ESTÁN EN LA TIENDA
        # ==================================

        no_encontrados = lista_valida[
            ~lista_valida["_clave"].isin(catalogo["_clave"])
        ].copy()

        with st.expander(
            f"SKU del XLS que no están en Tiendanube "
            f"({no_encontrados['_clave'].nunique()})"
        ):

            st.dataframe(
                no_encontrados[
                    ["SKU", "Articulo", "Precio_nuevo"]
                ].drop_duplicates("SKU"),
                hide_index=True,
                use_container_width=True
            )

        # ==================================
        # VALIDACIÓN DE SEGURIDAD
        # ==================================

        resultado = catalogo.drop(
            columns=[
                "_clave",
                "Precio_anterior",
                "Precio_nuevo"
            ]
        )

        otras_columnas = [
            c for c in original.columns
            if c != "Precio"
        ]

        seguridad_ok = (
            len(resultado) == len(original)
            and resultado.columns.tolist()
            == original.columns.tolist()
            and resultado[otras_columnas].equals(
                original[otras_columnas]
            )
        )

        if not seguridad_ok:
            st.error(
                "Se detectaron cambios fuera de la "
                "columna Precio. Descarga bloqueada."
            )
            st.stop()

        st.success(
            "✅ Validación correcta: solo se modificó "
            "la columna Precio. No se agregaron productos."
        )

        # ==================================
        # DESCARGAR CSV FINAL
        # ==================================

        csv_final = resultado.to_csv(
            index=False,
            sep=separador,
            lineterminator="\n"
        ).encode(encoding)

        st.download_button(
            "📥 Descargar CSV actualizado para Tiendanube",
            data=csv_final,
            file_name="tiendanube_precios_actualizados.csv",
            mime="text/csv",
            disabled=modificados == 0
        )

        st.caption(
            "El CSV conserva todos los productos "
            "originales de Tiendanube. Los artículos "
            "que solo existen en el XLS no se agregan."
        )

        st.warning(
            "Antes de importar masivamente, guardá "
            "una copia del CSV original y probá "
            "la actualización con un producto."
        )

    except Exception as e:
        st.error(f"No pude procesar los archivos: {e}")
