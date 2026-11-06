        if codigos_repetidos:
            st.warning(
                f"⚠️ Se detectaron **{codigos_repetidos} SKU duplicados** en la lista XLS "
                f"({len(repetidos_xls)} filas). "
                "Si las repeticiones tienen el mismo precio válido, se usa una sola vez; "
                "si hay precios distintos, ese SKU no se actualiza."
            )
            with st.expander("Ver los SKU duplicados del XLS"):
                st.dataframe(
                    repetidos_xls[["SKU", "Articulo_XLS", "Precio_nuevo"]].sort_values("SKU"),
                    hide_index=True, use_container_width=True,
                )
        else:
            st.info("No se encontraron SKU duplicados en la lista XLS.")

        st.subheader("Estos son los precios que cambiaron")
        columnas_resumen = ["SKU"]
        if "Nombre" in cambios.columns:
            columnas_resumen.append("Nombre")
        resumen = cambios[columnas_resumen].copy()
        resumen["Precio anterior"] = cambios["Precio_anterior"].map(precio_decimal).to_numpy()
        resumen["Precio nuevo"] = cambios["Precio"].map(precio_decimal).to_numpy()
        resumen["Diferencia ($)"] = resumen.apply(
            lambda fila: (fila["Precio nuevo"] - fila["Precio anterior"])
            if fila["Precio anterior"] is not None and fila["Precio nuevo"] is not None else None,
            axis=1,
        )
        resumen["Cambio (%)"] = resumen.apply(
            lambda fila: round(float(100 * fila["Diferencia ($)"] / fila["Precio anterior"]), 2)
            if fila["Diferencia ($)"] is not None and fila["Precio anterior"] not in (None, Decimal("0")) else None,
            axis=1,
        )
        resumen["Movimiento"] = resumen["Diferencia ($)"].map(
            lambda valor: "⬆ Aumentó" if valor is not None and valor > 0
            else ("⬇ Bajó" if valor is not None and valor < 0 else "Sin comparación")
        )
        if resumen.empty:
            st.info("No hay precios diferentes para actualizar. No se genera un archivo innecesario.")
        else:
            st.dataframe(resumen, use_container_width=True, hide_index=True)
            st.download_button(
                "Descargar informe de precios que cambiaron",
                resumen.to_csv(index=False).encode("utf-8-sig"),
                file_name="informe_cambios_precios.csv", mime="text/csv",
            )

        # Solo los duplicados con precios contradictorios o códigos ambiguos en
        # Tiendanube se bloquean; los duplicados idénticos del XLS se informan arriba.
        if not conflictos_lista.empty or not conflictos_tienda.empty:
            with st.expander("⚠️ Revisar códigos ambiguos (no se actualizaron)", expanded=True):
                if not conflictos_lista.empty:
                    st.warning(
                        f"Hay {len(claves_con_precios_distintos)} códigos en el XLS "
                        "con precios diferentes para un mismo SKU. No se actualizaron."
                    )
                    st.dataframe(
                        conflictos_lista[["SKU", "Articulo_XLS", "Precio_nuevo"]],
                        hide_index=True, use_container_width=True,
                    )
                if not conflictos_tienda.empty:
                    st.warning(
                        f"Hay {conflictos_tienda['_clave'].nunique()} códigos repetidos "
                        "en el catálogo de Tiendanube. Se omitieron por seguridad."
                    )
                    columnas_alerta = [c for c in ["SKU", "Nombre", "Identificador de URL", "Precio"] if c in conflictos_tienda.columns]
                    st.dataframe(conflictos_tienda[columnas_alerta], hide_index=True, use_container_width=True)

        sin_coincidencia = lista_valida[~lista_valida["_clave"].isin(catalogo["_clave"])].copy()
        with st.expander(f"SKU de la lista que no están en Tiendanube ({sin_coincidencia['_clave'].nunique()} códigos)"):
            st.dataframe(
                sin_coincidencia.drop_duplicates("_clave").drop(columns=["_clave", "_precio_final"]),
                hide_index=True,
            )

        # Mantiene nombres y orden de todas las columnas, y modifica solo Precio.
        resultado = catalogo.drop(columns=["_clave", "Precio_anterior", "Precio_nuevo"])
        columnas_no_precio = [c for c in catalogo_original.columns if c != "Precio"]
        seguridad_ok = (
            len(resultado) == len(catalogo_original)
            and resultado.columns.tolist() == catalogo_original.columns.tolist()
            and resultado[columnas_no_precio].equals(catalogo_original[columnas_no_precio])
        )
        if not seguridad_ok:
            st.error("Validación de seguridad fallida: se detectaron diferencias fuera de Precio. No se permite descargar.")
            st.stop()

        st.success("Validación completada: misma cantidad de filas, mismas columnas, mismos SKU e identificadores; únicamente puede variar Precio.")
        st.caption("Los productos que están solo en el XLS quedan excluidos. Los productos de Tiendanube sin coincidencia mantienen su precio original.")
        csv_resultado = resultado.to_csv(index=False, sep=sep, lineterminator="\n").encode(encoding)
        st.download_button("Descargar CSV actualizado para Tiendanube", csv_resultado,
                           file_name="tiendanube_precios_actualizados.csv", mime="text/csv",
                           disabled=len(cambios) == 0)
        if not sin_coincidencia.empty:
            st.download_button("Descargar códigos del XLS que no están en Tiendanube",
                               sin_coincidencia.drop_duplicates("_clave").drop(columns=["_clave", "_precio_final"]).to_csv(index=False).encode("utf-8-sig"),
                               file_name="codigos_no_encontrados.csv", mime="text/csv")
        st.warning("Antes de una actualización masiva, importá una copia de prueba de un producto, verificá el resultado y respaldá el CSV original. Al importar, seleccioná modificar productos existentes y desactivá actualización de stock.")
    except Exception as e:
        st.error(f"No pude procesar los archivos: {e}")
