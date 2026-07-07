"""
JwCAD 配線・配管集計アプリ (Streamlit)
"""

import io
import tempfile
import os
from pathlib import Path
import streamlit as st
import pandas as pd

from jwcad_summary import (
    extract_text_from_jww,
    extract_text_from_txt,
    extract_text_from_pdf,
    parse_lines,
    aggregate,
    aggregate_free_cables,
    aggregate_bollards,
)

# ─────────────────────────────────────────
#  ページ設定
# ─────────────────────────────────────────

VERSION = "v2.3"

st.set_page_config(
    page_title="JwCAD 配線・配管 集計ツール",
    page_icon="⚡",
    layout="wide",
)

st.title("⚡ JwCAD 配線・配管 集計ツール")
st.caption(f"JWWファイルまたはテキストファイルを読み込み、配線種・配管種・付帯設備の集計表を作成します。　{VERSION}")

# ─────────────────────────────────────────
#  サイドバー: 入力
# ─────────────────────────────────────────

with st.sidebar:
    st.header("📂 ファイル入力")
    uploaded = st.file_uploader(
        "ファイルをアップロード",
        type=["jww", "jw_", "txt", "pdf"],
        help="JWW・テキスト・PDFに対応しています",
    )

    st.divider()
    st.header("✏️ テキスト直接入力")
    manual_text = st.text_area(
        "図面の文字情報を貼り付け",
        height=300,
        placeholder="例:\n露出立下 HIVE(70) 8×1(8m)\n6.6kV CVT38sq 9×1(9m)\nバリカー(電動) ×3",
    )
    run_manual = st.button("直接入力で集計", type="primary", use_container_width=True)

    st.divider()
    st.info(
        "**対応ファイル**\n"
        "- .jww / .jw_（JwCAD図面）\n"
        "- .pdf\n"
        "- .txt（テキスト）\n\n"
        "**対応表記**\n"
        "- 配管: 露出/埋設 + HIVE・FEP\n"
        "- ケーブル: CVT・IV 系\n"
        "- 付帯設備: バリカー\n"
        "- **「既設」と書かれた行は除外**"
    )

# ─────────────────────────────────────────
#  処理
# ─────────────────────────────────────────

lines = []
source_name = ""

if uploaded is not None:
    ext = Path(uploaded.name).suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(uploaded.read())
        tmp_path = tmp.name
    try:
        if ext in (".jww", ".jw_"):
            lines = extract_text_from_jww(tmp_path)
        elif ext == ".pdf":
            lines = extract_text_from_pdf(tmp_path)
        else:
            lines = extract_text_from_txt(tmp_path)
    finally:
        os.unlink(tmp_path)
    source_name = uploaded.name

elif run_manual and manual_text.strip():
    lines = [l.strip() for l in manual_text.splitlines() if l.strip()]
    source_name = "直接入力"

# ─────────────────────────────────────────
#  結果表示
# ─────────────────────────────────────────

if not lines:
    st.info("左のサイドバーからファイルをアップロードするか、テキストを貼り付けて「集計」ボタンを押してください。")
else:
    # 解析
    conduits, cables, free_cables, bollards = parse_lines(lines)
    cable_totals, conduit_totals = aggregate(conduits, cables)
    free_cable_totals = aggregate_free_cables(free_cables)
    bollard_totals = aggregate_bollards(bollards)

    st.success(f"✅ **{source_name}** を解析しました")

    # ─── 抽出テキスト（折りたたみ） ───
    with st.expander(f"抽出テキスト ({len(lines)} 行)", expanded=False):
        st.code("\n".join(lines), language=None)

    st.divider()

    # ─────────────────────────────────────────
    #  集計表: 3カラムレイアウト
    # ─────────────────────────────────────────

    col1, col2, col3 = st.columns([1, 1.4, 0.8])

    # ── 配線種 ──
    with col1:
        st.subheader("📋 配線種")
        if cable_totals:
            CABLE_ORDER = ["6.6kVCVT38sq", "CVT150sq", "IV38sq", "IV14sq", "IV5.5sq"]
            ordered = CABLE_ORDER + [k for k in cable_totals if k not in CABLE_ORDER]
            rows = [
                {"配線種": k, "全長": f"{cable_totals[k]} m"}
                for k in ordered if k in cable_totals
            ]
            df_cable = pd.DataFrame(rows)
            st.dataframe(df_cable, hide_index=True, use_container_width=True)
        else:
            st.warning("ケーブル情報が見つかりませんでした")

    # ── 配管種 ──
    with col2:
        st.subheader("🔧 配管種")
        if conduit_totals:
            rows = []
            for inst, ctype, cabs, length in conduit_totals:
                rows.append({
                    "設置": inst,
                    "配管種": ctype,
                    "全長": f"{length} m",
                    "内線": " / ".join(cabs) if cabs else "―",
                })
            df_conduit = pd.DataFrame(rows)
            st.dataframe(df_conduit, hide_index=True, use_container_width=True)
        else:
            st.warning("配管情報が見つかりませんでした")

    # ── 付帯設備 ──
    with col3:
        st.subheader("🚧 付帯設備")
        if bollard_totals:
            rows = [{"種別": label, "数量": f"{qty} 台"} for label, qty in bollard_totals.items()]
            df_bollard = pd.DataFrame(rows)
            st.dataframe(df_bollard, hide_index=True, use_container_width=True)
        else:
            st.info("バリカーは検出されませんでした")

    # ── 配管なしケーブル ──
    if free_cable_totals:
        st.subheader("🔌 配管なしケーブル（充電器内・ポール内・キュービクル内など）")
        rows = [
            {"設置場所": loc, "ケーブル種": ctype, "全長": f"{ln} m"}
            for loc, ctype, ln in free_cable_totals
        ]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    st.divider()

    # ─────────────────────────────────────────
    #  Excel ダウンロード
    # ─────────────────────────────────────────

    def build_excel(cable_totals, conduit_totals, free_cable_totals, bollard_totals) -> bytes:
        import openpyxl
        from openpyxl.styles import Alignment, Font, Border, Side, PatternFill

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "サマリ"

        thin = Side(style="thin")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)
        header_fill = PatternFill("solid", fgColor="DDEEFF")
        bold = Font(bold=True)
        center = Alignment(horizontal="center", vertical="center")
        left_align = Alignment(horizontal="left", vertical="center")

        def cell(r, c, value, font=None, fill=None, align=None):
            cl = ws.cell(row=r, column=c, value=value)
            if font:  cl.font = font
            if fill:  cl.fill = fill
            if align: cl.alignment = align
            cl.border = border
            return cl

        row = 1

        # タイトル
        ws.merge_cells(f"A{row}:D{row}")
        c = ws.cell(row=row, column=1, value="サマリ")
        c.font = Font(bold=True, size=14)
        c.alignment = center
        row += 1

        # 配線種
        ws.merge_cells(f"A{row}:D{row}")
        cell(row, 1, "配線種", bold, header_fill, center)
        row += 1

        CABLE_ORDER = ["6.6kVCVT38sq", "CVT150sq", "IV38sq", "IV14sq", "IV5.5sq"]
        ordered = CABLE_ORDER + [k for k in cable_totals if k not in CABLE_ORDER]
        for k in ordered:
            if k not in cable_totals:
                continue
            cell(row, 1, "", align=center)
            cell(row, 2, k, align=center)
            ws.merge_cells(f"C{row}:D{row}")
            cell(row, 3, f"全長{cable_totals[k]}m", align=center)
            ws.cell(row=row, column=4).border = border
            row += 1

        row += 1

        # 配管種
        ws.merge_cells(f"A{row}:D{row}")
        cell(row, 1, "配管種", bold, header_fill, center)
        row += 1
        for install_type in ["露出", "埋設"]:
            for inst, ctype, cabs, length in conduit_totals:
                if inst != install_type:
                    continue
                cable_note = " / ".join(cabs) if cabs else ""
                cell(row, 1, inst, align=center)
                cell(row, 2, ctype, align=center)
                cell(row, 3, f"全長{length}m", align=center)
                cell(row, 4, f"({cable_note})" if cable_note else "", align=left_align)
                row += 1

        row += 1

        # 配管なしケーブル
        if free_cable_totals:
            ws.merge_cells(f"A{row}:D{row}")
            cell(row, 1, "配管なしケーブル", bold, header_fill, center)
            row += 1
            for loc, ctype, ln in free_cable_totals:
                cell(row, 1, loc, align=center)
                cell(row, 2, ctype, align=center)
                ws.merge_cells(f"C{row}:D{row}")
                cell(row, 3, f"全長{ln}m", align=center)
                ws.cell(row=row, column=4).border = border
                row += 1
            row += 1

        # 付帯設備
        ws.merge_cells(f"A{row}:D{row}")
        cell(row, 1, "付帯設備", bold, header_fill, center)
        row += 1
        if bollard_totals:
            for label, qty in bollard_totals.items():
                cell(row, 1, label, align=center)
                ws.merge_cells(f"B{row}:D{row}")
                cell(row, 2, f"{qty}台", align=center)
                ws.cell(row=row, column=3).border = border
                ws.cell(row=row, column=4).border = border
                row += 1
        else:
            ws.merge_cells(f"A{row}:D{row}")
            cell(row, 1, "（検出されませんでした）", align=left_align)
            row += 1

        ws.column_dimensions["A"].width = 12
        ws.column_dimensions["B"].width = 20
        ws.column_dimensions["C"].width = 14
        ws.column_dimensions["D"].width = 30

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()


    excel_bytes = build_excel(cable_totals, conduit_totals, free_cable_totals, bollard_totals)
    stem = Path(source_name).stem if source_name != "直接入力" else "集計結果"

    st.download_button(
        label="📥 Excelファイルをダウンロード",
        data=excel_bytes,
        file_name=f"{stem}_サマリ.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=False,
    )
