import hashlib
import math
import os
import secrets
import shutil
import sqlite3
import subprocess
import sys
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import flet as ft

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm, mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas as _pdf_canvas
    _HAS_REPORTLAB = True
except ImportError:
    _HAS_REPORTLAB = False

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    _HAS_ARABIC_SHAPING = True
except ImportError:
    _HAS_ARABIC_SHAPING = False


# ===========================================================================
# CONFIG
# ===========================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("SIERRA_DB_PATH", os.path.join(BASE_DIR, "sierra_store.db"))
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
DATA_DIR = os.path.join(BASE_DIR, "data")
INVOICES_DIR = os.path.join(DATA_DIR, "invoices")
REPORTS_DIR = os.path.join(DATA_DIR, "reports")
REPORT_CATEGORIES = ["sales", "purchases", "shipping", "profits",
                     "expenses", "inventory", "returns", "customers",
                     "products", "suppliers", "general"]

ROLE_ADMIN = "admin"
ROLE_USER = "user"
VALID_ROLES = (ROLE_ADMIN, ROLE_USER)
INVOICE_START_NUMBER = 1000
CUSTOMER_CODE_START = 1001
POINTS_PER_PIECE = 10
POINTS_PER_EGP = 5
WELCOME_BONUS_POINTS = 50
COMMISSION_CODE = "__COMMISSION__"
QUICK_CUSTOMER_CODE = "SF-QUICK"
QUICK_CUSTOMER_NAME = "عميل سريع"
RETURN_REASON_DEFECT = "defect"
RETURN_REASON_NORMAL = "normal"
RETURN_REASON_LABELS = {"defect": "عيب مصنعي", "normal": "مرتجع عادي"}

DEFAULT_SETTINGS = {
    "shop_name": "SIERRA STORE",
    "invoice_header": "سييرا ستور\nSIERRA STORE",
    "invoice_footer": "شكراً لتعاملكم معنا!\nالبضاعة لا تُرد بعد 3 أيام.",
    "currency_symbol": "ج.م",
    "printer_paper_width": "80mm",
    "login_logo_path": "",
    "printer_thermal": "",
    "printer_a4": "",
}

# ===========================================================================
# STYLE
# ===========================================================================
BG_BLACK = "#050505"
BG_SIDEBAR = "#0d0d0d"
BG_CARD = "#1e1e1e"
BG_CARD_HOVER = "#2a2a2a"
BG_INPUT = "#1a1a1a"
BG_HEADER = "#0d0d0d"
BORDER = "#2e2e2e"
BORDER_HOVER = "#4a4a4a"
TEXT_PRIMARY = "#ffffff"
TEXT_SECONDARY = "#b5b5b5"
TEXT_MUTED = "#767676"
ACCENT = "#ffffff"
ACCENT_HOVER = "#d4d4d4"
DANGER = "#ff4d4d"
SUCCESS = "#3ddc84"
WARNING = "#ffb340"
INFO = "#4d9fff"
SP_XS, SP_SM, SP_MD, SP_LG, SP_XL = 4, 8, 16, 24, 32
RADIUS_SM, RADIUS_MD, RADIUS_LG = 6, 10, 16
SIDEBAR_WIDTH = 260
HEADER_HEIGHT = 76
FS_TITLE, FS_SECTION, FS_BODY, FS_SMALL, FS_TINY = 24, 16, 14, 13, 12
BTN_H, BTN_PAD_H, BTN_PAD_V = 44, 18, 10
ACTION_BTN_SLOT = 24
TABLE_COL_GAP = 4
SERIAL_COL_W = 55
SOFT_LIMIT = 5000


# ===========================================================================
# STYLE HELPERS
# ===========================================================================
def _hv_card(e):
    a = e.data == "true"
    e.control.bgcolor = BG_CARD_HOVER if a else BG_CARD
    e.control.border = ft.border.all(1, BORDER_HOVER if a else BORDER)
    e.control.update()


def _hv_primary(e):
    e.control.bgcolor = ACCENT_HOVER if e.data == "true" else ACCENT
    e.control.update()


def _hv_ghost(e):
    a = e.data == "true"
    e.control.bgcolor = BG_CARD_HOVER if a else "transparent"
    e.control.border = ft.border.all(1, BORDER_HOVER if a else BORDER)
    e.control.update()


def _hv_danger(e):
    a = e.data == "true"
    e.control.bgcolor = "#3a1414" if a else "transparent"
    e.control.border = ft.border.all(1, DANGER if a else BORDER)
    e.control.update()


def card(content, padding=SP_MD, hover=True, expand=False, on_click=None):
    c = ft.Container(content=content, bgcolor=BG_CARD,
                     border=ft.border.all(1, BORDER),
                     border_radius=RADIUS_MD, padding=padding,
                     expand=expand, on_click=on_click, ink=False)
    if hover:
        c.on_hover = _hv_card
    return c


def text_field(label, value="", width=None, password=False, multiline=False,
               on_change=None, on_submit=None, prefix_icon=None,
               keyboard_type=None, hint=None, autofocus=False,
               read_only=False, expand=False):
    return ft.TextField(
        label=label, value=value, width=width, password=password,
        can_reveal_password=password, multiline=multiline,
        min_lines=4 if multiline else 1, max_lines=12 if multiline else 1,
        on_change=on_change, on_submit=on_submit, prefix_icon=prefix_icon,
        keyboard_type=keyboard_type, hint_text=hint, autofocus=autofocus,
        read_only=read_only, expand=expand, bgcolor=BG_INPUT,
        border_color=BORDER, focused_border_color=ACCENT,
        border_radius=RADIUS_SM, color=TEXT_PRIMARY, cursor_color=ACCENT,
        text_size=FS_BODY, content_padding=12,
        label_style=ft.TextStyle(color=TEXT_SECONDARY, size=FS_SMALL))


def dropdown(label, options, value=None, width=None, on_change=None):
    return ft.Dropdown(
        label=label, value=value, width=width,
        options=[ft.dropdown.Option(o) for o in options],
        on_change=on_change, bgcolor=BG_INPUT, border_color=BORDER,
        focused_border_color=ACCENT, border_radius=RADIUS_SM,
        color=TEXT_PRIMARY, text_size=FS_BODY, content_padding=12,
        label_style=ft.TextStyle(color=TEXT_SECONDARY, size=FS_SMALL))


def keyed_dropdown(label, options, value=None, width=None, on_change=None):
    return ft.Dropdown(
        label=label, value=value, width=width,
        options=[ft.dropdown.Option(key=k, text=t) for k, t in options],
        on_change=on_change, bgcolor=BG_INPUT, border_color=BORDER,
        focused_border_color=ACCENT, border_radius=RADIUS_SM,
        color=TEXT_PRIMARY, text_size=FS_BODY, content_padding=12,
        label_style=ft.TextStyle(color=TEXT_SECONDARY, size=FS_SMALL))


def primary_button(text, on_click, icon=None, width=None, height=BTN_H,
                   expand=False, disabled=False):
    content = (ft.Row([ft.Icon(icon, size=16, color=BG_BLACK),
                       ft.Text(text, color=BG_BLACK,
                               weight=ft.FontWeight.W_700, size=FS_BODY)],
                      alignment=ft.MainAxisAlignment.CENTER,
                      spacing=6, tight=True)
               if icon else
               ft.Text(text, color=BG_BLACK,
                       weight=ft.FontWeight.W_700, size=FS_BODY))
    c = ft.Container(
        content=content, bgcolor=ACCENT if not disabled else BG_CARD,
        border_radius=RADIUS_SM,
        padding=ft.padding.symmetric(horizontal=BTN_PAD_H, vertical=BTN_PAD_V),
        on_click=on_click if not disabled else None, width=width,
        height=height, expand=expand, alignment=ft.alignment.center,
        ink=not disabled)
    if not disabled:
        c.on_hover = _hv_primary
    return c


def ghost_button(text, on_click, icon=None, width=None, height=BTN_H,
                 expand=False, color=None, danger=False):
    fg = color or TEXT_PRIMARY
    content = (ft.Row([ft.Icon(icon, size=16, color=fg),
                       ft.Text(text, color=fg,
                               weight=ft.FontWeight.W_600, size=FS_BODY)],
                      alignment=ft.MainAxisAlignment.CENTER,
                      spacing=6, tight=True)
               if icon else
               ft.Text(text, color=fg, weight=ft.FontWeight.W_600,
                       size=FS_BODY))
    c = ft.Container(
        content=content, bgcolor="transparent",
        border=ft.border.all(1, BORDER), border_radius=RADIUS_SM,
        padding=ft.padding.symmetric(horizontal=BTN_PAD_H, vertical=BTN_PAD_V),
        on_click=on_click, width=width, height=height, expand=expand,
        alignment=ft.alignment.center, ink=True)
    c.on_hover = _hv_danger if danger else _hv_ghost
    return c


def page_title(title, subtitle=""):
    items = [ft.Text(title, color=TEXT_PRIMARY, size=FS_TITLE,
                     weight=ft.FontWeight.W_800)]
    if subtitle:
        items.append(ft.Text(subtitle, color=TEXT_MUTED, size=FS_SMALL))
    return ft.Column(items, spacing=2, tight=True)


def section_title(text):
    return ft.Text(text, color=TEXT_PRIMARY, size=FS_SECTION,
                   weight=ft.FontWeight.W_700)


def divider():
    return ft.Container(height=1, bgcolor=BORDER)


def empty_state(message, icon=ft.icons.INBOX):
    return ft.Container(
        content=ft.Column([ft.Icon(icon, size=44, color=TEXT_MUTED),
                           ft.Text(message, color=TEXT_MUTED, size=FS_BODY)],
                          alignment=ft.MainAxisAlignment.CENTER,
                          horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                          spacing=SP_SM),
        alignment=ft.alignment.center, padding=SP_XL, expand=True)


def snack(page, message, kind="info"):
    colors = {"info": (BG_CARD, TEXT_PRIMARY),
              "success": ("#0f2a18", SUCCESS),
              "error": ("#2a0f0f", DANGER),
              "warning": ("#2a200f", WARNING)}
    bg, fg = colors.get(kind, colors["info"])
    try:
        page.open(ft.SnackBar(ft.Text(message, color=fg, size=FS_BODY),
                              bgcolor=bg))
    except Exception:
        pass


def confirm_dialog(page, title, message, on_confirm,
                   confirm_text="تأكيد", cancel_text="إلغاء", danger=False):
    def close(e=None):
        page.close(dlg)

    def confirm(e):
        page.close(dlg)
        on_confirm()

    dlg = ft.AlertDialog(
        modal=True, bgcolor=BG_CARD,
        title=ft.Text(title, color=TEXT_PRIMARY,
                      weight=ft.FontWeight.W_700, size=FS_SECTION),
        content=ft.Text(message, color=TEXT_SECONDARY, size=FS_BODY),
        actions=[ghost_button(cancel_text, close, width=120),
                 ghost_button(confirm_text, confirm, width=120,
                              color=DANGER if danger else BG_BLACK,
                              danger=danger)])
    page.open(dlg)


def chip(text, color=TEXT_SECONDARY, bg=None):
    return ft.Container(
        content=ft.Text(text, color=color, size=FS_TINY,
                        weight=ft.FontWeight.W_600),
        bgcolor=bg or BG_INPUT,
        padding=ft.padding.symmetric(horizontal=8, vertical=3),
        border_radius=999)


# ===========================================================================
# DATA DIRECTORIES
# ===========================================================================
def ensure_data_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(INVOICES_DIR, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)
    for cat in REPORT_CATEGORIES:
        os.makedirs(os.path.join(REPORTS_DIR, cat), exist_ok=True)


def invoice_pdf_path(invoice_number, kind="thermal"):
    today = date.today()
    sub = os.path.join(INVOICES_DIR, str(today.year), f"{today.month:02d}")
    os.makedirs(sub, exist_ok=True)
    safe_kind = "thermal" if kind == "thermal" else "a4"
    try:
        num = int(invoice_number)
    except (TypeError, ValueError):
        num = 0
    return os.path.join(sub, f"invoice_{num:06d}_{safe_kind}.pdf")


def return_pdf_path(return_code, kind="thermal"):
    today = date.today()
    sub = os.path.join(INVOICES_DIR, str(today.year), f"{today.month:02d}")
    os.makedirs(sub, exist_ok=True)
    safe_code = (return_code or "R0000").replace("/", "_")
    safe_kind = "thermal" if kind == "thermal" else "a4"
    return os.path.join(sub, f"return_{safe_code}_{safe_kind}.pdf")


def report_pdf_path(category, base_name):
    cat = (category or "general").strip().lower()
    if cat not in REPORT_CATEGORIES:
        cat = "general"
    sub = os.path.join(REPORTS_DIR, cat)
    os.makedirs(sub, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(sub, f"{base_name}_{ts}.pdf")


# ===========================================================================
# PRINTER HELPERS
# ===========================================================================
def list_printers():
    try:
        import win32print  # type: ignore
        flags = (win32print.PRINTER_ENUM_LOCAL
                 | win32print.PRINTER_ENUM_CONNECTIONS)
        return sorted({p[2] for p in win32print.EnumPrinters(flags)
                       if len(p) > 2 and p[2]})
    except Exception:
        pass
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "Get-Printer | Select-Object -ExpandProperty Name"],
            stderr=subprocess.DEVNULL, timeout=6,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).decode("utf-8", "ignore")
        return sorted({l.strip() for l in out.splitlines() if l.strip()})
    except Exception:
        return []


def send_pdf_to_printer(path, printer_name="", page=None):
    if not os.path.isfile(path):
        if page:
            snack(page, f"الملف غير موجود: {path}", "error")
        return False
    try:
        if printer_name:
            try:
                import win32api  # type: ignore
                win32api.ShellExecute(0, "printto", path,
                                      f'"{printer_name}"', ".", 0)
                return True
            except Exception:
                pass
        try:
            os.startfile(path, "print")  # type: ignore
            return True
        except Exception:
            pass
        open_with_system_viewer(path)
        return True
    except Exception as ex:
        if page:
            snack(page, str(ex), "error")
        return False


def open_with_system_viewer(path):
    try:
        if hasattr(os, "startfile"):
            os.startfile(path)  # type: ignore
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as ex:
        raise RuntimeError(f"فشل فتح الملف: {ex}")


# ===========================================================================
# INLINE ACTIONS (real ft.IconButton)
# ===========================================================================
def _action_icon_btn(page, act):
    def _h(e):
        try:
            act["handler"]()
        except Exception as ex:
            snack(page, str(ex), kind="error")

    color = DANGER if act.get("danger") else act.get("color", TEXT_PRIMARY)
    btn = ft.IconButton(
        icon=act.get("icon", ft.icons.EDIT),
        icon_size=15, icon_color=color,
        tooltip=act.get("label", ""), on_click=_h,
    )
    try:
        btn.style = ft.ButtonStyle(
            padding=ft.padding.all(2),
            shape=ft.RoundedRectangleBorder(radius=4),
        )
    except Exception:
        pass
    return ft.Container(content=btn, width=ACTION_BTN_SLOT,
                        height=ACTION_BTN_SLOT,
                        alignment=ft.alignment.center)


def _actions_cell(page, actions, width):
    if not actions:
        return ft.Container(width=width, height=ACTION_BTN_SLOT + 4)
    btns = [_action_icon_btn(page, a) for a in actions]
    return ft.Container(
        content=ft.Row(btns, spacing=0, tight=True,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
        width=width, height=ACTION_BTN_SLOT + 6,
        alignment=ft.alignment.center_left)


def _action_col_width(n_acts):
    if n_acts <= 0:
        return 0
    return n_acts * ACTION_BTN_SLOT + 8


def data_table(page, columns, rows, empty_message="لا توجد سجلات.",
               raw_data=None, row_actions_builder=None, on_row_click=None,
               show_serial=True):
    if not rows:
        return empty_state(empty_message)

    if show_serial:
        columns = [("مسلسل", SERIAL_COL_W)] + list(columns)
        rows = [[ft.Text(str(i + 1), color=TEXT_SECONDARY, size=FS_SMALL,
                         weight=ft.FontWeight.W_600)] + list(r)
                for i, r in enumerate(rows)]

    has_actions = bool(row_actions_builder and raw_data is not None)

    max_acts = 0
    if has_actions:
        for rd in raw_data[:len(rows)]:
            try:
                acts = row_actions_builder(rd) or []
                max_acts = max(max_acts, len(acts))
            except Exception:
                pass
    action_col_w = _action_col_width(max_acts)

    data_cols = []
    for h, w in columns:
        data_cols.append(
            ft.DataColumn(
                ft.Container(
                    content=ft.Text(h, color=TEXT_SECONDARY,
                                    size=FS_TINY,
                                    weight=ft.FontWeight.W_700,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS),
                    width=w, alignment=ft.alignment.center_left)))
    if has_actions:
        data_cols.append(
            ft.DataColumn(
                ft.Container(
                    content=ft.Text("الإجراءات", color=TEXT_SECONDARY,
                                    size=FS_TINY,
                                    weight=ft.FontWeight.W_700, max_lines=1),
                    width=action_col_w)))

    data_rows = []
    for idx, r in enumerate(rows):
        cells: List[ft.DataCell] = []
        for i, c in enumerate(r):
            wrap = ft.Container(c, width=columns[i][1],
                                alignment=ft.alignment.center_left)
            if on_row_click and raw_data is not None and idx < len(raw_data):
                wrap.on_click = (
                    lambda e, rd=raw_data[idx]: on_row_click(rd)
                )
                wrap.ink = True
            cells.append(ft.DataCell(wrap))
        if has_actions:
            acts = []
            if idx < len(raw_data):
                try:
                    acts = row_actions_builder(raw_data[idx]) or []
                except Exception:
                    acts = []
            cells.append(ft.DataCell(_actions_cell(page, acts, action_col_w)))
        data_rows.append(ft.DataRow(cells=cells))

    table = ft.DataTable(
        columns=data_cols, rows=data_rows, bgcolor=BG_CARD,
        vertical_lines=ft.border.BorderSide(1, BORDER),
        horizontal_lines=ft.border.BorderSide(1, BORDER),
        heading_row_color=BG_CARD_HOVER,
        heading_row_height=40, data_row_min_height=40,
        data_row_max_height=50, column_spacing=TABLE_COL_GAP,
        divider_thickness=0)

    return ft.Column(
        [ft.Row([table], scroll=ft.ScrollMode.AUTO, tight=True,
                vertical_alignment=ft.CrossAxisAlignment.START)],
        spacing=0, expand=True, scroll=ft.ScrollMode.AUTO)


# ===========================================================================
# IN-APP PREVIEW DIALOGS
# ===========================================================================
def _receipt_line(text, size=10, bold=False, align="right", color="#050505"):
    return ft.Container(
        content=ft.Text(text or "", color=color, size=size,
                        weight=ft.FontWeight.W_700 if bold
                        else ft.FontWeight.W_400,
                        text_align=(ft.TextAlign.RIGHT if align == "right"
                                    else (ft.TextAlign.CENTER
                                          if align == "center"
                                          else ft.TextAlign.LEFT))),
        alignment=(ft.alignment.center_right if align == "right"
                   else (ft.alignment.center if align == "center"
                         else ft.alignment.center_left)),
        padding=ft.padding.only(top=1))


def open_thermal_preview(page, invoice):
    rows = []
    rows.append(_receipt_line("سييرا ستور", 16, bold=True, align="center"))
    rows.append(_receipt_line("SIERRA STORE", 10, align="center"))
    rows.append(ft.Container(height=4))
    rows.append(_receipt_line(
        f"العميل: {invoice.get('customer_name') or '—'}", 10))
    rows.append(_receipt_line(
        f"الهاتف: {invoice.get('customer_phone') or '—'}", 10))
    rows.append(_receipt_line(
        f"الكود: {invoice.get('customer_code') or '—'}", 10))
    if invoice.get("customer_code") != QUICK_CUSTOMER_CODE:
        rows.append(_receipt_line(
            f"النقاط الحالية: {invoice.get('_loyalty_balance', 0)}", 10))
    if invoice.get("customer_address"):
        rows.append(_receipt_line(
            f"العنوان: {invoice['customer_address']}", 10))
    rows.append(ft.Container(height=1, bgcolor="#000000",
                             margin=ft.padding.symmetric(vertical=4)))
    rows.append(_receipt_line(
        f"التاريخ: {invoice['created_at'][:16]}", 10))
    rows.append(_receipt_line(
        f"رقم الفاتورة: #{invoice.get('invoice_number', invoice['id'])}",
        10, bold=True))
    cashier_display = (invoice.get("cashier_code")
                       or invoice.get("cashier_name") or "—")
    rows.append(_receipt_line(f"الكاشير: {cashier_display}", 10))
    rows.append(_receipt_line(
        "الحالة: "
        f"{'قيد الدفع' if invoice.get('status') == 'pending' else 'تم الدفع'}",
        10))
    rows.append(ft.Container(height=1, bgcolor="#000000",
                             margin=ft.padding.symmetric(vertical=4)))
    rows.append(_receipt_line("الصنف  ·  العدد  ·  السعر  ·  الإجمالي",
                              9, bold=True))
    rows.append(ft.Container(height=1, bgcolor="#000000",
                             margin=ft.padding.symmetric(vertical=4)))
    for it in invoice.get("items", []):
        name = (it["product_name"] or "")[:20]
        rows.append(_receipt_line(
            f"{name}  ·  {it['quantity']}  ·  "
            f"{it['price']:.2f}  ·  {it['total_price']:.2f}", 9))
    rows.append(ft.Container(height=1, bgcolor="#000000",
                             margin=ft.padding.symmetric(vertical=4)))
    if invoice.get("discount", 0) > 0:
        rows.append(_receipt_line(
            f"الخصم: -{invoice['discount']:.2f} ج.م", 10, bold=True))
    rows.append(_receipt_line(
        f"الإجمالي: {invoice['net_total']:.2f} ج.م", 13, bold=True))
    earned = invoice.get("_points_earned", 0)
    if earned:
        rows.append(_receipt_line(f"النقاط المكتسبة: +{earned}", 9))
    rows.append(ft.Container(height=6))
    for line in (get_invoice_footer() or "").splitlines():
        rows.append(_receipt_line(line, 9, align="center"))

    paper = ft.Container(
        content=ft.Column(rows, spacing=0, tight=True,
                          scroll=ft.ScrollMode.AUTO),
        bgcolor="#ffffff", padding=12, width=320, height=520,
        border_radius=4, border=ft.border.all(1, "#888888"))

    def do_print(e):
        try:
            path = invoice_pdf_path(
                invoice.get("invoice_number", invoice["id"]), "thermal")
            generate_pdf_receipt(invoice, path)
            send_pdf_to_printer(
                path, get_setting("printer_thermal", "") or "", page)
            snack(page, "تم إرسال الإيصال للطباعة.", "success")
        except Exception as ex:
            snack(page, str(ex), "error")
        finally:
            page.close(dlg)

    def do_save(e):
        try:
            path = invoice_pdf_path(
                invoice.get("invoice_number", invoice["id"]), "thermal")
            generate_pdf_receipt(invoice, path)
            snack(page, f"حُفظ: {path}", "success")
        except Exception as ex:
            snack(page, str(ex), "error")

    def close(e=None):
        page.close(dlg)

    dlg = ft.AlertDialog(
        modal=True, bgcolor=BG_CARD,
        title=ft.Text("معاينة الإيصال الحراري", color=TEXT_PRIMARY,
                      weight=ft.FontWeight.W_700, size=FS_SECTION),
        content=paper,
        actions=[ghost_button("إغلاق", close, width=100),
                 ghost_button("حفظ", do_save, icon=ft.icons.SAVE, width=110),
                 primary_button("طباعة", do_print, icon=ft.icons.PRINT,
                                width=140)])
    page.open(dlg)


def open_thermal_return_preview(page, ret):
    rows = []
    rows.append(_receipt_line("سييرا ستور", 16, bold=True, align="center"))
    rows.append(_receipt_line("SIERRA STORE", 10, align="center"))
    rows.append(_receipt_line("إيصال مرتجع", 12, bold=True, align="center"))
    rows.append(ft.Container(height=4))
    rows.append(_receipt_line(
        f"كود المرتجع: {ret.get('return_code') or '—'}", 10, bold=True))
    rows.append(_receipt_line(
        f"الفاتورة: #{ret.get('invoice_number') or '—'}", 10))
    rows.append(_receipt_line(
        f"العميل: {ret.get('customer_name') or '—'}", 10))
    rows.append(_receipt_line(
        f"التاريخ: {ret['created_at'][:16]}", 10))
    rows.append(ft.Container(height=1, bgcolor="#000000",
                             margin=ft.padding.symmetric(vertical=4)))
    rows.append(_receipt_line("الصنف  ·  العدد  ·  السعر  ·  الإجمالي",
                              9, bold=True))
    rows.append(ft.Container(height=1, bgcolor="#000000",
                             margin=ft.padding.symmetric(vertical=4)))
    for it in ret.get("items", []):
        name = (it["product_name"] or "")[:20]
        reason_mark = ("عيب" if it.get("reason_type") == RETURN_REASON_DEFECT
                       else "عادي")
        rows.append(_receipt_line(
            f"[{reason_mark}] {name}  ·  {it['quantity']}  ·  "
            f"{it['price']:.2f}  ·  {it['total_price']:.2f}", 9))
    rows.append(ft.Container(height=1, bgcolor="#000000",
                             margin=ft.padding.symmetric(vertical=4)))
    rows.append(_receipt_line(
        f"إجمالي الاسترداد: {ret['total_refund']:.2f} ج.م", 12, bold=True))
    if ret.get("notes"):
        rows.append(_receipt_line(f"ملاحظات: {ret['notes']}", 9))
    rows.append(ft.Container(height=6))
    for line in (get_invoice_footer() or "").splitlines():
        rows.append(_receipt_line(line, 9, align="center"))

    paper = ft.Container(
        content=ft.Column(rows, spacing=0, tight=True,
                          scroll=ft.ScrollMode.AUTO),
        bgcolor="#ffffff", padding=12, width=320, height=520,
        border_radius=4, border=ft.border.all(1, "#888888"))

    def do_print(e):
        try:
            path = return_pdf_path(
                ret.get("return_code") or "R0000", "thermal")
            generate_pdf_return_receipt(ret, path)
            send_pdf_to_printer(
                path, get_setting("printer_thermal", "") or "", page)
            snack(page, "تم إرسال الإيصال للطباعة.", "success")
        except Exception as ex:
            snack(page, str(ex), "error")
        finally:
            page.close(dlg)

    def do_save(e):
        try:
            path = return_pdf_path(
                ret.get("return_code") or "R0000", "thermal")
            generate_pdf_return_receipt(ret, path)
            snack(page, f"حُفظ: {path}", "success")
        except Exception as ex:
            snack(page, str(ex), "error")

    def close(e=None):
        page.close(dlg)

    dlg = ft.AlertDialog(
        modal=True, bgcolor=BG_CARD,
        title=ft.Text("معاينة إيصال المرتجع (حراري)", color=TEXT_PRIMARY,
                      weight=ft.FontWeight.W_700, size=FS_SECTION),
        content=paper,
        actions=[ghost_button("إغلاق", close, width=100),
                 ghost_button("حفظ", do_save, icon=ft.icons.SAVE, width=110),
                 primary_button("طباعة", do_print, icon=ft.icons.PRINT,
                                width=140)])
    page.open(dlg)


def open_a4_invoice_preview(page, invoice):
    items_rows = []
    for it in invoice.get("items", []):
        items_rows.append([
            ft.Text(it["product_name"] or "—", color=TEXT_PRIMARY,
                    size=FS_SMALL, max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS),
            ft.Text(str(it["quantity"]), color=TEXT_PRIMARY, size=FS_SMALL),
            ft.Text(f"{it['price']:.2f}", color=TEXT_PRIMARY, size=FS_SMALL),
            ft.Text(f"{it['total_price']:.2f}", color=TEXT_PRIMARY,
                    size=FS_SMALL),
        ])
    items_table = data_table(
        page,
        [("الصنف", 220), ("الكمية", 60), ("السعر", 80), ("الإجمالي", 90)],
        items_rows, "لا أصناف.", show_serial=False)

    cashier_display = (invoice.get("cashier_code")
                       or invoice.get("cashier_name") or "—")
    info = ft.Column([
        ft.Text(f"فاتورة #{invoice.get('invoice_number', invoice['id'])}",
                color=TEXT_PRIMARY, size=FS_SECTION,
                weight=ft.FontWeight.W_800),
        ft.Text(f"العميل: {invoice.get('customer_name') or '—'}",
                color=TEXT_PRIMARY, size=FS_BODY),
        ft.Text(f"الهاتف: {invoice.get('customer_phone') or '—'}",
                color=TEXT_SECONDARY, size=FS_SMALL),
        ft.Text(f"العنوان: {invoice.get('customer_address') or '—'}",
                color=TEXT_SECONDARY, size=FS_SMALL),
        ft.Text(f"التاريخ: {invoice['created_at'][:16]}",
                color=TEXT_SECONDARY, size=FS_SMALL),
        ft.Text(f"الكاشير: {cashier_display}",
                color=TEXT_SECONDARY, size=FS_SMALL),
        ft.Text(f"الإجمالي: {money_str(invoice['net_total'])}",
                color=SUCCESS, size=FS_BODY, weight=ft.FontWeight.W_700),
    ], spacing=4)

    content = ft.Column([
        info, divider(), ft.Container(height=SP_SM), items_table,
    ], spacing=SP_SM, width=620, height=460, scroll=ft.ScrollMode.AUTO)

    def do_print(e):
        try:
            path = invoice_pdf_path(
                invoice.get("invoice_number", invoice["id"]), "a4")
            generate_pdf_invoice_a4(invoice, path)
            send_pdf_to_printer(path, get_setting("printer_a4", "") or "", page)
            snack(page, "تم إرسال الفاتورة للطباعة.", "success")
        except Exception as ex:
            snack(page, str(ex), "error")
        finally:
            page.close(dlg)

    def do_save(e):
        try:
            path = invoice_pdf_path(
                invoice.get("invoice_number", invoice["id"]), "a4")
            generate_pdf_invoice_a4(invoice, path)
            snack(page, f"حُفظ: {path}", "success")
        except Exception as ex:
            snack(page, str(ex), "error")

    def close(e=None):
        page.close(dlg)

    dlg = ft.AlertDialog(
        modal=True, bgcolor=BG_CARD,
        title=ft.Text("معاينة الفاتورة A4", color=TEXT_PRIMARY,
                      weight=ft.FontWeight.W_700, size=FS_SECTION),
        content=content,
        actions=[ghost_button("إغلاق", close, width=100),
                 ghost_button("حفظ", do_save, icon=ft.icons.SAVE, width=110),
                 primary_button("طباعة", do_print, icon=ft.icons.PRINT,
                                width=140)])
    page.open(dlg)


def open_report_preview(page, title, headers, rows, summary_lines,
                        category, base_name, from_date="", to_date=""):
    dt_cols = [ft.DataColumn(ft.Container(
        ft.Text(h, color=TEXT_SECONDARY, size=FS_TINY,
                weight=ft.FontWeight.W_700),
        alignment=ft.alignment.center_left)) for h in headers]
    dt_rows = []
    for r in rows:
        dt_rows.append(ft.DataRow(cells=[
            ft.DataCell(ft.Container(ft.Text(str(c), color=TEXT_PRIMARY,
                                             size=FS_SMALL, max_lines=1,
                                             overflow=ft.TextOverflow.ELLIPSIS),
                                     alignment=ft.alignment.center_left))
            for c in r]))
    table = ft.DataTable(
        columns=dt_cols, rows=dt_rows, bgcolor=BG_INPUT,
        vertical_lines=ft.border.BorderSide(1, BORDER),
        horizontal_lines=ft.border.BorderSide(1, BORDER),
        heading_row_color=BG_CARD_HOVER, heading_row_height=38,
        data_row_min_height=34, data_row_max_height=44,
        column_spacing=6, divider_thickness=0)

    summary_holder = ft.Column(spacing=4)
    for line in (summary_lines or []):
        summary_holder.controls.append(
            ft.Text(line, color=SUCCESS, size=FS_SMALL,
                    weight=ft.FontWeight.W_700,
                    text_align=ft.TextAlign.RIGHT))

    content = ft.Column([
        ft.Text(f"عدد السجلات: {len(rows)}",
                color=TEXT_MUTED, size=FS_TINY),
        ft.Container(
            content=ft.Row([table], scroll=ft.ScrollMode.AUTO, tight=True),
            height=400),
        divider(), summary_holder,
    ], spacing=SP_SM, width=720, height=520, scroll=ft.ScrollMode.AUTO)

    def do_print(e):
        try:
            path = report_pdf_path(category, base_name)
            generate_pdf_report(title, headers, rows, path,
                                from_date, to_date,
                                summary_lines=summary_lines)
            send_pdf_to_printer(path, get_setting("printer_a4", "") or "", page)
            snack(page, "تم إرسال التقرير للطباعة.", "success")
        except Exception as ex:
            snack(page, str(ex), "error")
        finally:
            page.close(dlg)

    def do_save(e):
        try:
            path = report_pdf_path(category, base_name)
            generate_pdf_report(title, headers, rows, path,
                                from_date, to_date,
                                summary_lines=summary_lines)
            snack(page, f"حُفظ: {path}", "success")
        except Exception as ex:
            snack(page, str(ex), "error")

    def close(e=None):
        page.close(dlg)

    dlg = ft.AlertDialog(
        modal=True, bgcolor=BG_CARD,
        title=ft.Text(title, color=TEXT_PRIMARY,
                      weight=ft.FontWeight.W_700, size=FS_SECTION),
        content=content,
        actions=[ghost_button("إغلاق", close, width=100),
                 ghost_button("حفظ", do_save, icon=ft.icons.SAVE, width=110),
                 primary_button("طباعة", do_print, icon=ft.icons.PRINT,
                                width=140)])
    page.open(dlg)


# ===========================================================================
# FLEXIBLE SEARCH
# ===========================================================================
def flexible_customer_search(term: str) -> List[Dict[str, Any]]:
    term = (term or "").strip()
    if not term:
        return get_all_customers()
    patterns = [f"%{term}%"]
    if term.isdigit():
        patterns.append(f"%SF-{term}%")
        patterns.append(f"%SF-{term}")
    ors, params = [], []
    for p in patterns:
        ors.append("(code LIKE ? OR name LIKE ? OR phone LIKE ?)")
        params.extend([p, p, p])
    q = ("SELECT * FROM customers WHERE " + " OR ".join(ors)
         + " ORDER BY id DESC LIMIT " + str(SOFT_LIMIT))
    with get_connection() as conn:
        rows = conn.execute(q, params).fetchall()
    return _rows_to_dicts(rows)


# ===========================================================================
# PDF HELPERS
# ===========================================================================
_REGISTERED: set = set()
_ARABIC_FONT = "Helvetica"


def _find_arabic_font():
    for p in (
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/tahoma.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/amiri/Amiri-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/GeezaPro.ttc",
    ):
        if os.path.exists(p):
            return p
    return None


def _register_font():
    global _ARABIC_FONT
    if not _HAS_REPORTLAB:
        return "Helvetica"
    if "ArabicFont" in _REGISTERED:
        return _ARABIC_FONT
    path = _find_arabic_font()
    if not path:
        return "Helvetica"
    try:
        pdfmetrics.registerFont(TTFont("ArabicFont", path))
        _REGISTERED.add("ArabicFont")
        _ARABIC_FONT = "ArabicFont"
        return "ArabicFont"
    except Exception:
        return "Helvetica"


def _shape(s: str) -> str:
    s = str(s)
    if not _HAS_ARABIC_SHAPING:
        return s
    try:
        return get_display(arabic_reshaper.reshape(s))
    except Exception:
        return s


def _require_pdf():
    if not _HAS_REPORTLAB:
        raise RuntimeError("مكتبة PDF غير مثبتة. شغّل:\n"
                           "pip install reportlab arabic-reshaper python-bidi")
    if not _HAS_ARABIC_SHAPING:
        raise RuntimeError("مكتبة دعم العربية غير مثبتة. شغّل:\n"
                           "pip install arabic-reshaper python-bidi")


def generate_pdf_report(title, headers, rows, filepath,
                        from_date="", to_date="", summary_lines=None):
    _require_pdf()
    font = _register_font()
    c = _pdf_canvas.Canvas(filepath, pagesize=A4)
    W, H = A4
    margin = 1.2 * cm

    def draw(x, y, text, size=10, align="left"):
        c.setFont(font, size)
        s = _shape(text)
        if align == "center":
            c.drawCentredString(x, y, s)
        elif align == "right":
            c.drawRightString(x, y, s)
        else:
            c.drawString(x, y, s)

    y = H - margin
    draw(W / 2, y, "سييرا ستور", 20, "center"); y -= 0.8 * cm
    draw(W / 2, y, "SIERRA STORE", 10, "center"); y -= 0.7 * cm
    draw(W / 2, y, title, 15, "center"); y -= 0.7 * cm
    if from_date or to_date:
        draw(W - margin, y,
             f"من: {from_date or '—'}   إلى: {to_date or '—'}",
             10, "right"); y -= 0.5 * cm
    draw(W - margin, y,
         f"تاريخ الطباعة: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
         9, "right"); y -= 0.6 * cm
    c.line(margin, y, W - margin, y); y -= 0.4 * cm

    n = max(1, len(headers))
    cw = (W - 2 * margin) / n

    def draw_header(yy):
        c.setFillColorRGB(0.9, 0.9, 0.9)
        c.rect(margin, yy - 0.6 * cm, W - 2 * margin, 0.6 * cm,
               fill=1, stroke=1)
        c.setFillColorRGB(0, 0, 0)
        for i, h in enumerate(reversed(headers)):
            x = margin + i * cw + cw / 2
            draw(x, yy - 0.42 * cm, h, 10, "center")
        return yy - 0.6 * cm

    y = draw_header(y)
    rh = 0.55 * cm
    for r in rows:
        if y < margin + 2 * cm:
            c.showPage(); y = H - margin
            draw(W / 2, y, title, 15, "center"); y -= 0.8 * cm
            y = draw_header(y)
        c.rect(margin, y - rh, W - 2 * margin, rh, fill=0, stroke=1)
        for i, cell in enumerate(reversed(r)):
            x = margin + i * cw + cw / 2
            draw(x, y - rh + 0.15 * cm, str(cell), 9, "center")
        y -= rh
    y -= 0.4 * cm
    draw(W - margin, y, f"عدد السجلات: {len(rows)}", 10, "right")
    y -= 0.4 * cm

    if summary_lines:
        y -= 0.3 * cm
        c.line(margin, y, W - margin, y); y -= 0.4 * cm
        for line in summary_lines:
            draw(W - margin, y, line, 11, "right")
            y -= 0.55 * cm
    c.save()


def generate_pdf_record(title, pairs, filepath):
    _require_pdf()
    font = _register_font()
    c = _pdf_canvas.Canvas(filepath, pagesize=A4)
    W, H = A4
    margin = 2 * cm

    def draw(x, y, text, size=12, align="left"):
        c.setFont(font, size)
        s = _shape(text)
        if align == "center":
            c.drawCentredString(x, y, s)
        elif align == "right":
            c.drawRightString(x, y, s)
        else:
            c.drawString(x, y, s)

    y = H - margin
    draw(W / 2, y, "سييرا ستور", 22, "center"); y -= 0.9 * cm
    draw(W / 2, y, "SIERRA STORE", 11, "center"); y -= 0.6 * cm
    draw(W / 2, y, title, 14, "center"); y -= 1.4 * cm

    for label, value in pairs:
        draw(margin, y, f"{label}:", 12, "left")
        draw(W - margin, y, str(value), 12, "right")
        y -= 0.55 * cm
        c.setStrokeColorRGB(0.88, 0.88, 0.88)
        c.line(margin, y + 0.15 * cm, W - margin, y + 0.15 * cm)
        y -= 0.15 * cm

    y -= 1.0 * cm
    draw(W / 2, y,
         f"تاريخ الطباعة: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
         9, "center")
    c.save()


def generate_pdf_invoice_a4(invoice, filepath):
    _require_pdf()
    font = _register_font()
    c = _pdf_canvas.Canvas(filepath, pagesize=A4)
    W, H = A4
    margin = 1.5 * cm

    def draw(x, y, text, size=10, align="left"):
        c.setFont(font, size)
        s = _shape(text)
        if align == "center":
            c.drawCentredString(x, y, s)
        elif align == "right":
            c.drawRightString(x, y, s)
        else:
            c.drawString(x, y, s)

    y = H - margin
    draw(W / 2, y, "سييرا ستور", 24, "center"); y -= 0.9 * cm
    draw(W / 2, y, "SIERRA STORE", 11, "center"); y -= 0.5 * cm
    draw(W / 2, y, "فاتورة مبيعات", 14, "center"); y -= 1.2 * cm

    box_h = 2.4 * cm
    c.setStrokeColorRGB(0.6, 0.6, 0.6)
    c.rect(margin, y - box_h, W - 2 * margin, box_h, fill=0, stroke=1)

    cy = y - 0.55 * cm
    draw(margin + 0.3 * cm, cy,
         f"اسم العميل: {invoice.get('customer_name') or '—'}", 11)
    draw(W - margin - 0.3 * cm, cy,
         f"رقم الفاتورة: #{invoice.get('invoice_number', invoice['id'])}",
         11, "right")
    cy -= 0.6 * cm
    draw(margin + 0.3 * cm, cy,
         f"الهاتف: {invoice.get('customer_phone') or '—'}", 10)
    draw(W - margin - 0.3 * cm, cy,
         f"التاريخ: {invoice['created_at'][:16]}", 10, "right")
    cy -= 0.6 * cm
    draw(margin + 0.3 * cm, cy,
         f"العنوان: {invoice.get('customer_address') or '—'}", 10)
    draw(W - margin - 0.3 * cm, cy,
         f"الحالة: "
         f"{'مدفوعة' if invoice.get('status') == 'paid' else 'قيد الدفع'}",
         10, "right")

    if invoice.get("waybill_number"):
        cy -= 0.6 * cm
        draw(margin + 0.3 * cm, cy,
             f"البوليصة: {invoice['waybill_number']}", 10)

    y -= (box_h + 0.4 * cm)

    usable = W - 2 * margin
    name_w = usable * 0.55
    qty_w = usable * 0.10
    price_w = usable * 0.175
    header_h = 0.65 * cm

    def draw_items_header(yy):
        c.setFillColorRGB(0.88, 0.88, 0.88)
        c.rect(margin, yy - header_h, usable, header_h, fill=1, stroke=1)
        c.setFillColorRGB(0, 0, 0)
        c.rect(margin, yy - header_h, usable, header_h, fill=0, stroke=1)
        hy = yy - header_h + 0.2 * cm
        draw(W - margin - 0.2 * cm, hy, "الصنف", 10, "right")
        draw(W - margin - name_w - 0.2 * cm, hy, "العدد", 10, "right")
        draw(W - margin - name_w - qty_w - 0.2 * cm, hy,
             "سعر القطعة", 10, "right")
        draw(W - margin - name_w - qty_w - price_w - 0.2 * cm, hy,
             "الإجمالي", 10, "right")
        return yy - header_h

    y = draw_items_header(y)

    row_h = 0.55 * cm
    for it in invoice.get("items", []):
        if y < margin + 3 * cm:
            c.showPage()
            y = H - margin
            draw(W / 2, y, "سييرا ستور", 20, "center"); y -= 0.8 * cm
            draw(W / 2, y,
                 f"فاتورة #{invoice.get('invoice_number', invoice['id'])}",
                 12, "center"); y -= 1.2 * cm
            y = draw_items_header(y)

        c.setStrokeColorRGB(0.6, 0.6, 0.6)
        c.rect(margin, y - row_h, usable, row_h, fill=0, stroke=1)
        ty = y - row_h + 0.15 * cm
        name = (it["product_name"] or "")[:45]
        draw(W - margin - 0.2 * cm, ty, name, 10, "right")
        draw(W - margin - name_w - 0.2 * cm, ty,
             str(it["quantity"]), 10, "right")
        draw(W - margin - name_w - qty_w - 0.2 * cm, ty,
             f"{it['price']:.2f}", 10, "right")
        draw(W - margin - name_w - qty_w - price_w - 0.2 * cm, ty,
             f"{it['total_price']:.2f}", 10, "right")
        y -= row_h

    y -= 0.5 * cm
    draw(W - margin, y,
         f"المجموع الفرعي: {invoice['subtotal']:.2f} ج.م", 11, "right")
    y -= 0.55 * cm
    if invoice.get("discount", 0) > 0:
        draw(W - margin, y,
             f"الخصم: -{invoice['discount']:.2f} ج.م", 11, "right")
        y -= 0.55 * cm
    draw(W - margin, y,
         f"الإجمالي النهائي: {invoice['net_total']:.2f} ج.م",
         13, "right")

    y -= 1.5 * cm
    for line in (get_invoice_footer() or "").splitlines():
        draw(W / 2, y, line, 9, "center"); y -= 0.4 * cm
    c.save()


def generate_pdf_receipt(invoice, filepath):
    _require_pdf()
    font = _register_font()
    page = (80 * mm, 297 * mm)
    c = _pdf_canvas.Canvas(filepath, pagesize=page)
    W, H = page
    margin = 3 * mm
    y = H - margin

    def draw(x, y, text, size=8, align="left"):
        c.setFont(font, size)
        s = _shape(text)
        if align == "center":
            c.drawCentredString(x, y, s)
        elif align == "right":
            c.drawRightString(x, y, s)
        else:
            c.drawString(x, y, s)

    def r_line(text, size=8, spacing_mm=4):
        nonlocal y
        draw(W - margin, y, text, size, "right")
        y -= spacing_mm * mm

    draw(W / 2, y, "سييرا ستور", 14, "center"); y -= 5 * mm
    draw(W / 2, y, "SIERRA STORE", 8, "center"); y -= 4 * mm

    r_line(f"العميل: {invoice.get('customer_name') or '—'}")
    r_line(f"الهاتف: {invoice.get('customer_phone') or '—'}")
    r_line(f"الكود: {invoice.get('customer_code') or '—'}")
    if invoice.get("customer_code") != QUICK_CUSTOMER_CODE:
        r_line(f"النقاط الحالية: {invoice.get('_loyalty_balance', 0)}")
    if invoice.get("customer_address"):
        r_line(f"العنوان: {invoice['customer_address']}")

    c.line(margin, y, W - margin, y); y -= 3 * mm

    r_line(f"التاريخ: {invoice['created_at'][:16]}")
    r_line(f"رقم الفاتورة: "
           f"#{invoice.get('invoice_number', invoice['id'])}")
    cashier_display = (invoice.get("cashier_code")
                       or invoice.get("cashier_name") or "—")
    r_line(f"الكاشير: {cashier_display}")
    r_line("الحالة: "
           f"{'قيد الدفع' if invoice.get('status') == 'pending' else 'تم الدفع'}")

    c.line(margin, y, W - margin, y); y -= 3 * mm

    draw(W - margin, y, "الصنف", 7, "right")
    draw(margin + 50 * mm, y, "العدد", 7, "center")
    draw(margin + 30 * mm, y, "السعر", 7, "center")
    draw(margin + 10 * mm, y, "الإجمالي", 7, "center")
    y -= 4 * mm
    c.line(margin, y, W - margin, y); y -= 3 * mm

    for it in invoice.get("items", []):
        draw(W - margin, y, (it["product_name"] or "")[:18], 7, "right")
        draw(margin + 50 * mm, y, str(it["quantity"]), 7, "center")
        draw(margin + 30 * mm, y, f"{it['price']:.2f}", 7, "center")
        draw(margin + 10 * mm, y, f"{it['total_price']:.2f}", 7, "center")
        y -= 4 * mm

    c.line(margin, y, W - margin, y); y -= 3 * mm

    if invoice.get("discount", 0) > 0:
        r_line(f"الخصم: -{invoice['discount']:.2f} ج.م")
    r_line(f"الإجمالي: {invoice['net_total']:.2f} ج.م", 10, 5)
    earned = invoice.get("_points_earned", 0)
    if earned:
        r_line(f"النقاط المكتسبة: +{earned}", 8)
    y -= 3 * mm
    for line in (get_invoice_footer() or "").splitlines():
        draw(W / 2, y, line, 7, "center"); y -= 3 * mm
    c.save()


def generate_pdf_return_receipt(ret, filepath):
    """80mm thermal return slip."""
    _require_pdf()
    font = _register_font()
    page = (80 * mm, 297 * mm)
    c = _pdf_canvas.Canvas(filepath, pagesize=page)
    W, H = page
    margin = 3 * mm
    y = H - margin

    def draw(x, y, text, size=8, align="left"):
        c.setFont(font, size)
        s = _shape(text)
        if align == "center":
            c.drawCentredString(x, y, s)
        elif align == "right":
            c.drawRightString(x, y, s)
        else:
            c.drawString(x, y, s)

    def r_line(text, size=8, spacing_mm=4):
        nonlocal y
        draw(W - margin, y, text, size, "right")
        y -= spacing_mm * mm

    draw(W / 2, y, "سييرا ستور", 14, "center"); y -= 5 * mm
    draw(W / 2, y, "SIERRA STORE", 8, "center"); y -= 4 * mm
    draw(W / 2, y, "إيصال مرتجع", 10, "center"); y -= 5 * mm

    r_line(f"كود المرتجع: {ret.get('return_code') or '—'}", 9)
    r_line(f"الفاتورة: #{ret.get('invoice_number') or '—'}")
    r_line(f"العميل: {ret.get('customer_name') or '—'}")
    r_line(f"التاريخ: {ret['created_at'][:16]}")

    c.line(margin, y, W - margin, y); y -= 3 * mm

    draw(W - margin, y, "الصنف", 7, "right")
    draw(margin + 50 * mm, y, "العدد", 7, "center")
    draw(margin + 30 * mm, y, "السعر", 7, "center")
    draw(margin + 10 * mm, y, "الإجمالي", 7, "center")
    y -= 4 * mm
    c.line(margin, y, W - margin, y); y -= 3 * mm

    for it in ret.get("items", []):
        reason_mark = ("عيب" if it.get("reason_type") == RETURN_REASON_DEFECT
                       else "عادي")
        draw(W - margin, y, f"[{reason_mark}] "
                            f"{(it['product_name'] or '')[:14]}", 7, "right")
        draw(margin + 50 * mm, y, str(it["quantity"]), 7, "center")
        draw(margin + 30 * mm, y, f"{it['price']:.2f}", 7, "center")
        draw(margin + 10 * mm, y, f"{it['total_price']:.2f}", 7, "center")
        y -= 4 * mm

    c.line(margin, y, W - margin, y); y -= 3 * mm
    r_line(f"إجمالي الاسترداد: {ret['total_refund']:.2f} ج.م", 10, 5)
    if ret.get("notes"):
        r_line(f"ملاحظات: {ret['notes']}", 8)
    y -= 3 * mm
    for line in (get_invoice_footer() or "").splitlines():
        draw(W / 2, y, line, 7, "center"); y -= 3 * mm
    c.save()


# ===========================================================================
# DATABASE
# ===========================================================================
@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today():
    return date.today().isoformat()


def _money(v):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return 0.0


def _row_to_dict(r):
    return dict(r) if r is not None else None


def _rows_to_dicts(rs):
    return [dict(r) for r in rs]


def _date_filter(col, df=None, dt=None):
    cl, ps = [], []
    if df:
        cl.append(f"date({col}) >= date(?)"); ps.append(df)
    if dt:
        cl.append(f"date({col}) <= date(?)"); ps.append(dt)
    return cl, ps


def round_to_5(amount):
    try:
        return int(float(amount) / 5 + 0.5) * 5
    except (TypeError, ValueError):
        return 0


def hash_password(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    d = hashlib.pbkdf2_hmac("sha256", str(pw).encode("utf-8"),
                            salt.encode("utf-8"), 120_000).hex()
    return f"{salt}${d}"


def verify_password(pw, stored):
    if not stored or "$" not in stored:
        return False
    salt, _ = stored.split("$", 1)
    return secrets.compare_digest(hash_password(pw, salt), stored)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin','user')),
    cashier_code TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',
    supplier TEXT NOT NULL DEFAULT '',
    cost_price REAL NOT NULL DEFAULT 0,
    wholesale_price REAL NOT NULL DEFAULT 0,
    stock_qty INTEGER NOT NULL DEFAULT 0,
    min_limit INTEGER NOT NULL DEFAULT 0,
    defect_qty INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_products_name ON products (name);
CREATE INDEX IF NOT EXISTS idx_products_supplier ON products (supplier);
CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_suppliers_name ON suppliers (name);
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    phone TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    governorate TEXT NOT NULL DEFAULT '',
    loyalty_points INTEGER NOT NULL DEFAULT 0,
    welcome_bonus_granted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers (phone);
CREATE INDEX IF NOT EXISTS idx_customers_code ON customers (code);
CREATE INDEX IF NOT EXISTS idx_customers_name ON customers (name);
CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number INTEGER UNIQUE,
    customer_id INTEGER,
    customer_code TEXT NOT NULL DEFAULT '',
    customer_name TEXT NOT NULL DEFAULT '',
    customer_phone TEXT NOT NULL DEFAULT '',
    customer_address TEXT NOT NULL DEFAULT '',
    customer_governorate TEXT NOT NULL DEFAULT '',
    total_items INTEGER NOT NULL DEFAULT 0,
    subtotal REAL NOT NULL DEFAULT 0,
    discount REAL NOT NULL DEFAULT 0,
    net_total REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','paid')),
    waybill_number TEXT NOT NULL DEFAULT '',
    loyalty_points_used INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    cashier_name TEXT NOT NULL DEFAULT '',
    cashier_code TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices (status);
CREATE INDEX IF NOT EXISTS idx_invoices_created ON invoices (created_at);
CREATE INDEX IF NOT EXISTS idx_invoices_customer ON invoices (customer_id);
CREATE INDEX IF NOT EXISTS idx_invoices_number ON invoices (invoice_number);
CREATE INDEX IF NOT EXISTS idx_invoices_waybill ON invoices (waybill_number);
CREATE INDEX IF NOT EXISTS idx_invoices_status_created
    ON invoices (status, created_at);
CREATE TABLE IF NOT EXISTS invoice_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    product_code TEXT NOT NULL,
    product_name TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    price REAL NOT NULL,
    total_price REAL NOT NULL,
    FOREIGN KEY (invoice_id) REFERENCES invoices (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_invoice_items_inv
    ON invoice_items (invoice_id);
CREATE INDEX IF NOT EXISTS idx_invoice_items_prod
    ON invoice_items (product_code);
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    amount REAL NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    date TEXT NOT NULL DEFAULT (date('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses (date);
CREATE INDEX IF NOT EXISTS idx_expenses_cat ON expenses (category);
CREATE TABLE IF NOT EXISTS purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_code TEXT NOT NULL,
    product_name TEXT NOT NULL,
    supplier TEXT NOT NULL DEFAULT '',
    quantity INTEGER NOT NULL DEFAULT 0,
    purchase_price REAL NOT NULL DEFAULT 0,
    selling_price REAL NOT NULL DEFAULT 0,
    total_cost REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_purchases_created ON purchases (created_at);
CREATE INDEX IF NOT EXISTS idx_purchases_product ON purchases (product_code);
CREATE TABLE IF NOT EXISTS loyalty_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    change_amount INTEGER NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    performed_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_loyalty_cust ON loyalty_log (customer_id);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS returns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    return_number INTEGER UNIQUE,
    return_code TEXT NOT NULL DEFAULT '',
    invoice_id INTEGER,
    invoice_number INTEGER,
    customer_id INTEGER,
    customer_name TEXT NOT NULL DEFAULT '',
    reason_type TEXT NOT NULL DEFAULT 'normal'
        CHECK (reason_type IN ('defect','normal')),
    notes TEXT NOT NULL DEFAULT '',
    total_refund REAL NOT NULL DEFAULT 0,
    created_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (invoice_id) REFERENCES invoices (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_returns_invoice ON returns (invoice_id);
CREATE INDEX IF NOT EXISTS idx_returns_created ON returns (created_at);
CREATE TABLE IF NOT EXISTS return_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    return_id INTEGER NOT NULL,
    product_code TEXT NOT NULL,
    product_name TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    price REAL NOT NULL,
    total_price REAL NOT NULL,
    reason_type TEXT NOT NULL DEFAULT 'normal'
        CHECK (reason_type IN ('defect','normal')),
    FOREIGN KEY (return_id) REFERENCES returns (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_return_items_return
    ON return_items (return_id);
CREATE INDEX IF NOT EXISTS idx_return_items_reason
    ON return_items (reason_type);
"""


def _ensure_quick_customer(conn):
    row = conn.execute("SELECT id FROM customers WHERE code=?",
                       (QUICK_CUSTOMER_CODE,)).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO customers (code, name, phone, address, governorate, "
            "loyalty_points, welcome_bonus_granted) "
            "VALUES (?, ?, ?, ?, ?, 0, 1)",
            (QUICK_CUSTOMER_CODE, QUICK_CUSTOMER_NAME, "0000", "0000", ""))


def initialize_database():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ensure_data_dirs()
    with get_connection() as conn:
        conn.executescript(SCHEMA_SQL)
        migrations = (
            "ALTER TABLE invoices ADD COLUMN invoice_number INTEGER",
            "ALTER TABLE invoices ADD COLUMN customer_id INTEGER",
            "ALTER TABLE invoices ADD COLUMN customer_code TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE invoices ADD COLUMN customer_address TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE invoices ADD COLUMN customer_governorate TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE invoices ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'",
            "ALTER TABLE invoices ADD COLUMN waybill_number TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE invoices ADD COLUMN loyalty_points_used INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE invoices ADD COLUMN cashier_code TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE products ADD COLUMN supplier TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE products ADD COLUMN defect_qty INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN cashier_code TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE customers ADD COLUMN welcome_bonus_granted INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE loyalty_log ADD COLUMN performed_by TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE return_items ADD COLUMN reason_type TEXT NOT NULL DEFAULT 'normal'",
            "ALTER TABLE returns ADD COLUMN return_code TEXT NOT NULL DEFAULT ''",
        )
        for stmt in migrations:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass
        # Safe unique index on return_code (created after the migration)
        try:
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_returns_code "
                "ON returns(return_code) WHERE return_code <> ''")
        except sqlite3.OperationalError:
            pass
        if conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] == 0:
            code = _next_cashier_code(conn)
            conn.execute(
                "INSERT INTO users (username, password, role, cashier_code) "
                "VALUES (?, ?, ?, ?)",
                ("admin", hash_password("admin123"), ROLE_ADMIN, code))
        for k, v in DEFAULT_SETTINGS.items():
            conn.execute("INSERT OR IGNORE INTO settings (key, value) "
                         "VALUES (?, ?)", (k, v))
        old = conn.execute("SELECT value FROM settings "
                           "WHERE key='currency_symbol'").fetchone()
        if old and old["value"] == "$":
            conn.execute("UPDATE settings SET value='ج.م' "
                         "WHERE key='currency_symbol'")
        _ensure_quick_customer(conn)
        rows = conn.execute("SELECT id FROM invoices "
                            "WHERE invoice_number IS NULL ORDER BY id").fetchall()
        if rows:
            m = conn.execute(
                "SELECT COALESCE(MAX(invoice_number), ?) AS m FROM invoices",
                (INVOICE_START_NUMBER,)).fetchone()
            n = max(int(m["m"]), INVOICE_START_NUMBER)
            for r in rows:
                n += 1
                conn.execute("UPDATE invoices SET invoice_number=? WHERE id=?",
                             (n, r["id"]))
        # Backfill missing return_code for any pre-existing returns
        rows = conn.execute("SELECT id FROM returns WHERE return_code = '' "
                            "OR return_code IS NULL ORDER BY id").fetchall()
        if rows:
            existing = conn.execute(
                "SELECT return_code FROM returns WHERE return_code <> '' "
                "AND return_code IS NOT NULL").fetchall()
            mx = 0
            for r in existing:
                c = r["return_code"] or ""
                if c.startswith("R"):
                    try:
                        n = int(c[1:])
                        if n > mx:
                            mx = n
                    except ValueError:
                        continue
            for r in rows:
                mx += 1
                conn.execute("UPDATE returns SET return_code=? WHERE id=?",
                             (f"R{mx:04d}", r["id"]))


def _next_cashier_code(conn):
    rows = conn.execute(
        "SELECT cashier_code FROM users "
        "WHERE cashier_code IS NOT NULL AND cashier_code<>''").fetchall()
    mx = 0
    for r in rows:
        c = r["cashier_code"] or ""
        if c.startswith("C-"):
            try:
                n = int(c[2:])
                if n > mx:
                    mx = n
            except ValueError:
                continue
    return f"C-{mx + 1:03d}"


def _next_return_code(conn):
    rows = conn.execute(
        "SELECT return_code FROM returns "
        "WHERE return_code IS NOT NULL AND return_code <> ''").fetchall()
    mx = 0
    for r in rows:
        c = r["return_code"] or ""
        if c.startswith("R"):
            try:
                n = int(c[1:])
                if n > mx:
                    mx = n
            except ValueError:
                continue
    return f"R{mx + 1:04d}"


# --- users ---
def create_user(username, password, role=ROLE_USER):
    username = (username or "").strip()
    if not username:
        raise ValueError("اسم المستخدم مطلوب.")
    if not password or len(password) < 4:
        raise ValueError("كلمة المرور قصيرة.")
    if role not in VALID_ROLES:
        raise ValueError("دور غير صالح.")
    with get_connection() as conn:
        code = _next_cashier_code(conn)
        try:
            cur = conn.execute(
                "INSERT INTO users (username, password, role, cashier_code) "
                "VALUES (?, ?, ?, ?)",
                (username, hash_password(password), role, code))
        except sqlite3.IntegrityError:
            raise ValueError(f"المستخدم '{username}' موجود.")
        return int(cur.lastrowid)


def authenticate(u, p):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?",
                           ((u or "").strip(),)).fetchone()
        if row is None or not verify_password(p, row["password"]):
            return None
        try:
            code = row["cashier_code"] or ""
        except (IndexError, KeyError):
            code = ""
        if not code:
            code = _next_cashier_code(conn)
            conn.execute("UPDATE users SET cashier_code=? WHERE id=?",
                         (code, row["id"]))
    return {"id": row["id"], "username": row["username"],
            "role": row["role"], "cashier_code": code}


def get_all_users():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, username, role, cashier_code, created_at FROM users "
            "ORDER BY username COLLATE NOCASE").fetchall()
    return _rows_to_dicts(rows)


def update_user_password(uid, pw):
    if not pw or len(pw) < 4:
        raise ValueError("كلمة المرور قصيرة.")
    with get_connection() as conn:
        cur = conn.execute("UPDATE users SET password=? WHERE id=?",
                           (hash_password(pw), uid))
    return cur.rowcount > 0


def update_user_role(uid, role):
    if role not in VALID_ROLES:
        raise ValueError("دور غير صالح.")
    with get_connection() as conn:
        u = conn.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone()
        if u is None:
            return False
        if u["role"] == ROLE_ADMIN and role != ROLE_ADMIN:
            if conn.execute("SELECT COUNT(*) AS c FROM users WHERE role=?",
                            (ROLE_ADMIN,)).fetchone()["c"] <= 1:
                raise ValueError("لا يمكن تخفيض آخر مسؤول.")
        cur = conn.execute("UPDATE users SET role=? WHERE id=?", (role, uid))
    return cur.rowcount > 0


def delete_user(uid):
    with get_connection() as conn:
        u = conn.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone()
        if u is None:
            return False
        if u["role"] == ROLE_ADMIN:
            if conn.execute("SELECT COUNT(*) AS c FROM users WHERE role=?",
                            (ROLE_ADMIN,)).fetchone()["c"] <= 1:
                raise ValueError("لا يمكن حذف آخر مسؤول.")
        cur = conn.execute("DELETE FROM users WHERE id=?", (uid,))
    return cur.rowcount > 0


def verify_admin_password(pw):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT password FROM users WHERE role=?", (ROLE_ADMIN,)).fetchall()
    for r in rows:
        if verify_password(pw, r["password"]):
            return True
    return False


# --- products ---
def add_product(code, name, supplier=""):
    code = (code or "").strip()
    name = (name or "").strip()
    if not code:
        raise ValueError("كود المنتج مطلوب.")
    if not name:
        raise ValueError("اسم المنتج مطلوب.")
    with get_connection() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO products (code, name, supplier) VALUES (?, ?, ?)",
                (code, name, (supplier or "").strip()))
        except sqlite3.IntegrityError:
            raise ValueError(f"كود '{code}' موجود.")
        return int(cur.lastrowid)


def update_product(pid, code, name, supplier=""):
    with get_connection() as conn:
        try:
            cur = conn.execute(
                "UPDATE products SET code=?, name=?, supplier=? WHERE id=?",
                ((code or "").strip(), (name or "").strip(),
                 (supplier or "").strip(), pid))
        except sqlite3.IntegrityError:
            raise ValueError("كود موجود.")
    return cur.rowcount > 0


def delete_product(pid):
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM products WHERE id=?", (pid,))
    return cur.rowcount > 0


def get_product_by_id(pid):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    return _row_to_dict(row)


def get_product_by_code(c):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM products WHERE code=?",
                           ((c or "").strip(),)).fetchone()
    return _row_to_dict(row)


def get_all_products(search=""):
    q = "SELECT * FROM products"
    ps = []
    if search:
        t = f"%{search.strip()}%"
        q += " WHERE code LIKE ? OR name LIKE ? OR supplier LIKE ?"
        ps += [t, t, t]
    q += " ORDER BY name COLLATE NOCASE LIMIT " + str(SOFT_LIMIT)
    with get_connection() as conn:
        return _rows_to_dicts(conn.execute(q, ps).fetchall())


def search_products(term, limit=50):
    term = (term or "").strip()
    if not term:
        return []
    p = f"%{term}%"
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM products WHERE code LIKE ? OR name LIKE ? "
            "OR supplier LIKE ? ORDER BY (stock_qty > 0) DESC, "
            "name COLLATE NOCASE LIMIT ?",
            (p, p, p, int(limit))).fetchall()
    return _rows_to_dicts(rows)


# --- suppliers ---
def add_supplier(name, phone="", address="", notes=""):
    name = (name or "").strip()
    if not name:
        raise ValueError("اسم المورد مطلوب.")
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO suppliers (name, phone, address, notes) "
            "VALUES (?, ?, ?, ?)",
            (name, phone.strip(), address.strip(), notes.strip()))
        return int(cur.lastrowid)


def update_supplier(sid, name, phone="", address="", notes=""):
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE suppliers SET name=?, phone=?, address=?, notes=? "
            "WHERE id=?",
            (name.strip(), phone.strip(), address.strip(), notes.strip(), sid))
    return cur.rowcount > 0


def delete_supplier(sid):
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM suppliers WHERE id=?", (sid,))
    return cur.rowcount > 0


def get_supplier_by_id(sid):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM suppliers WHERE id=?", (sid,)).fetchone()
    return _row_to_dict(row)


def get_all_suppliers(search=""):
    q = "SELECT * FROM suppliers"
    ps = []
    if search:
        t = f"%{search.strip()}%"
        q += " WHERE name LIKE ? OR phone LIKE ? OR address LIKE ?"
        ps += [t, t, t]
    q += " ORDER BY name COLLATE NOCASE LIMIT " + str(SOFT_LIMIT)
    with get_connection() as conn:
        return _rows_to_dicts(conn.execute(q, ps).fetchall())


# --- customers ---
def _next_customer_code(conn):
    rows = conn.execute("SELECT code FROM customers").fetchall()
    mx = CUSTOMER_CODE_START - 1
    for r in rows:
        c = r["code"] or ""
        if c.startswith("SF-") and c != QUICK_CUSTOMER_CODE:
            try:
                n = int(c[3:])
                if n > mx:
                    mx = n
            except ValueError:
                continue
    return f"SF-{mx + 1}"


def add_customer(name, phone="", address="", governorate=""):
    name = (name or "").strip()
    if not name:
        raise ValueError("اسم العميل مطلوب.")
    with get_connection() as conn:
        code = _next_customer_code(conn)
        cur = conn.execute(
            "INSERT INTO customers (code, name, phone, address, governorate) "
            "VALUES (?, ?, ?, ?, ?)",
            (code, name, phone.strip(), address.strip(), governorate.strip()))
        return int(cur.lastrowid), code


def update_customer(cid, name, phone="", address="", governorate=""):
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE customers SET name=?, phone=?, address=?, governorate=? "
            "WHERE id=?",
            (name.strip(), phone.strip(), address.strip(),
             governorate.strip(), cid))
    return cur.rowcount > 0


def delete_customer(cid):
    with get_connection() as conn:
        row = conn.execute("SELECT code FROM customers WHERE id=?",
                           (cid,)).fetchone()
        if row is not None and row["code"] == QUICK_CUSTOMER_CODE:
            raise ValueError("لا يمكن حذف العميل السريع.")
        cur = conn.execute("DELETE FROM customers WHERE id=?", (cid,))
    return cur.rowcount > 0


def get_customer_by_id(cid):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM customers WHERE id=?", (cid,)).fetchone()
    return _row_to_dict(row)


def get_customer_by_code(code):
    c = (code or "").strip().upper()
    if not c:
        return None
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM customers WHERE code=?", (c,)).fetchone()
    return _row_to_dict(row)


def get_quick_customer():
    return get_customer_by_code(QUICK_CUSTOMER_CODE)


def get_all_customers(search=""):
    q = "SELECT * FROM customers"
    ps = []
    if search:
        t = f"%{search.strip()}%"
        q += " WHERE code LIKE ? OR name LIKE ? OR phone LIKE ?"
        ps += [t, t, t]
    q += " ORDER BY id DESC LIMIT " + str(SOFT_LIMIT)
    with get_connection() as conn:
        return _rows_to_dicts(conn.execute(q, ps).fetchall())


def add_loyalty_points(cid, amount, reason="مكافأة", performed_by=""):
    amount = int(amount)
    with get_connection() as conn:
        conn.execute(
            "UPDATE customers SET loyalty_points=loyalty_points+? WHERE id=?",
            (amount, cid))
        conn.execute(
            "INSERT INTO loyalty_log (customer_id, change_amount, reason, "
            "performed_by) VALUES (?, ?, ?, ?)",
            (cid, amount, reason, performed_by or "system"))


def get_loyalty_log(cid, limit=200):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM loyalty_log WHERE customer_id=? "
            "ORDER BY id DESC LIMIT ?", (cid, int(limit))).fetchall()
    return _rows_to_dicts(rows)


# --- invoices ---
def _next_invoice_number(conn):
    m = conn.execute(
        "SELECT COALESCE(MAX(invoice_number), ?) AS m FROM invoices",
        (INVOICE_START_NUMBER,)).fetchone()
    return max(int(m["m"]), INVOICE_START_NUMBER) + 1


def get_next_invoice_number():
    with get_connection() as conn:
        return _next_invoice_number(conn)


def create_invoice(customer_id, customer_code, customer_name,
                   customer_phone, customer_address, customer_governorate,
                   items, discount=0.0, cashier_name="", cashier_code="",
                   loyalty_points_used=0):
    items = list(items or [])
    if not items:
        raise ValueError("لا أصناف.")
    discount = _money(discount)
    if discount < 0:
        raise ValueError("خصم سالب.")
    loyalty_points_used = max(0, int(loyalty_points_used))
    is_quick = (customer_code == QUICK_CUSTOMER_CODE)
    welcome_granted = False
    with get_connection() as conn:
        lines, demand, cache = [], {}, {}
        for raw in items:
            code = str(raw.get("product_code") or "").strip()
            if not code:
                raise ValueError("كود مطلوب.")
            qty = int(raw.get("quantity", 0))
            if qty <= 0:
                raise ValueError(f"كمية خاطئة '{code}'.")
            is_fee = bool(raw.get("is_fee", False))
            if is_fee:
                price = _money(raw.get("price", 0))
                name = (raw.get("product_name") or "رسوم").strip()
                lines.append({"product_code": code,
                              "product_name": name,
                              "quantity": qty, "price": price,
                              "total_price": _money(price * qty),
                              "is_fee": True})
                continue
            p = cache.get(code)
            if p is None:
                p = conn.execute("SELECT * FROM products WHERE code=?",
                                 (code,)).fetchone()
                if p is None:
                    raise ValueError(f"'{code}' غير موجود.")
                cache[code] = p
            price = _money(raw.get("price", p["wholesale_price"]))
            demand[code] = demand.get(code, 0) + qty
            lines.append({"product_code": code,
                          "product_name": p["name"], "quantity": qty,
                          "price": price,
                          "total_price": _money(price * qty),
                          "is_fee": False})
        for code, q in demand.items():
            if int(cache[code]["stock_qty"]) < q:
                raise ValueError(
                    f"مخزون '{cache[code]['name']}' غير كافٍ "
                    f"(المتاح {cache[code]['stock_qty']}).")
        subtotal = _money(sum(l["total_price"] for l in lines))
        physical_items_count = sum(l["quantity"] for l in lines
                                   if not l.get("is_fee"))
        if discount > subtotal:
            raise ValueError("خصم كبير.")
        net = _money(subtotal - discount)
        inv_num = _next_invoice_number(conn)
        cur = conn.execute(
            """INSERT INTO invoices
               (invoice_number, customer_id, customer_code, customer_name,
                customer_phone, customer_address, customer_governorate,
                total_items, subtotal, discount, net_total, status,
                loyalty_points_used, created_at, cashier_name, cashier_code)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)""",
            (inv_num, customer_id, customer_code, customer_name,
             customer_phone, customer_address, customer_governorate,
             physical_items_count, subtotal, discount, net,
             loyalty_points_used, _now(), cashier_name, cashier_code))
        inv_id = int(cur.lastrowid)
        for l in lines:
            conn.execute(
                """INSERT INTO invoice_items
                   (invoice_id, product_code, product_name, quantity,
                    price, total_price) VALUES (?, ?, ?, ?, ?, ?)""",
                (inv_id, l["product_code"], l["product_name"], l["quantity"],
                 l["price"], l["total_price"]))
            if not l.get("is_fee"):
                conn.execute("UPDATE products SET stock_qty=stock_qty-? "
                             "WHERE code=?",
                             (l["quantity"], l["product_code"]))

        # Welcome bonus — skip for quick customer
        if customer_id and not is_quick:
            cust = conn.execute(
                "SELECT welcome_bonus_granted FROM customers WHERE id=?",
                (customer_id,)).fetchone()
            if cust is not None and int(cust["welcome_bonus_granted"] or 0) == 0:
                conn.execute(
                    "UPDATE customers "
                    "SET loyalty_points=loyalty_points+?, "
                    "    welcome_bonus_granted=1 WHERE id=?",
                    (WELCOME_BONUS_POINTS, customer_id))
                conn.execute(
                    "INSERT INTO loyalty_log (customer_id, change_amount, "
                    "reason, performed_by) VALUES (?, ?, ?, ?)",
                    (customer_id, WELCOME_BONUS_POINTS,
                     "مكافأة ترحيبية (أول فاتورة)",
                     cashier_code or cashier_name or "system"))
                welcome_granted = True

        # Loyalty earning — skip for quick customer
        if customer_id and not is_quick:
            earned = physical_items_count * POINTS_PER_PIECE
            net_change = earned - loyalty_points_used
            if net_change != 0:
                conn.execute(
                    "UPDATE customers SET loyalty_points=loyalty_points+? "
                    "WHERE id=?", (net_change, customer_id))
                conn.execute(
                    "INSERT INTO loyalty_log (customer_id, change_amount, "
                    "reason, performed_by) VALUES (?, ?, ?, ?)",
                    (customer_id, net_change,
                     f"فاتورة #{inv_num} (مكتسبة {earned}, "
                     f"مستخدمة {loyalty_points_used})",
                     cashier_code or cashier_name or "system"))

    inv = get_invoice(inv_id)
    if inv is not None:
        inv["_welcome_bonus_granted"] = welcome_granted
    return inv


def get_invoice(inv_id):
    with get_connection() as conn:
        h = conn.execute("SELECT * FROM invoices WHERE id=?", (inv_id,)).fetchone()
        if h is None:
            return None
        items = conn.execute(
            "SELECT * FROM invoice_items WHERE invoice_id=? ORDER BY id",
            (inv_id,)).fetchall()
    inv = dict(h)
    inv["items"] = _rows_to_dicts(items)
    return inv


def get_invoice_by_number(number):
    try:
        n = int(number)
    except (TypeError, ValueError):
        return None
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM invoices WHERE invoice_number=?",
                           (n,)).fetchone()
    return _row_to_dict(row)


def enrich_invoice_for_print(inv):
    if not inv:
        return inv
    try:
        cid = inv.get("customer_id")
        if cid:
            cust = get_customer_by_id(cid)
            if cust:
                inv["_loyalty_balance"] = cust["loyalty_points"]
        if "_loyalty_balance" not in inv:
            inv["_loyalty_balance"] = 0
        total_physical = sum(it["quantity"] for it in inv.get("items", [])
                             if it.get("product_code") != COMMISSION_CODE)
        inv["_points_earned"] = (0 if inv.get("customer_code") ==
                                 QUICK_CUSTOMER_CODE
                                 else total_physical * POINTS_PER_PIECE)
    except Exception:
        pass
    return inv


def update_invoice(inv_id, customer_name=None, customer_phone=None,
                   customer_address=None, customer_governorate=None,
                   discount=None, status=None, waybill_number=None):
    with get_connection() as conn:
        inv = conn.execute("SELECT * FROM invoices WHERE id=?",
                           (inv_id,)).fetchone()
        if inv is None:
            return False
        fields, params = [], []
        if customer_name is not None:
            fields.append("customer_name=?"); params.append(customer_name.strip())
        if customer_phone is not None:
            fields.append("customer_phone=?"); params.append(customer_phone.strip())
        if customer_address is not None:
            fields.append("customer_address=?")
            params.append(customer_address.strip())
        if customer_governorate is not None:
            fields.append("customer_governorate=?")
            params.append(customer_governorate.strip())
        if discount is not None:
            d = _money(discount)
            sub = _money(inv["subtotal"])
            if d < 0 or d > sub:
                raise ValueError("خصم غير صالح.")
            fields.append("discount=?"); params.append(d)
            fields.append("net_total=?"); params.append(_money(sub - d))
        if status is not None:
            if status not in ("pending", "paid"):
                raise ValueError("حالة غير صالحة.")
            fields.append("status=?"); params.append(status)
        if waybill_number is not None:
            fields.append("waybill_number=?")
            params.append(str(waybill_number).strip())
        if not fields:
            return True
        params.append(inv_id)
        conn.execute(f"UPDATE invoices SET {', '.join(fields)} WHERE id=?",
                     params)
    return True


def delete_invoice(inv_id, performed_by=""):
    with get_connection() as conn:
        inv = conn.execute("SELECT * FROM invoices WHERE id=?",
                           (inv_id,)).fetchone()
        if inv is None:
            return False
        items = conn.execute(
            "SELECT product_code, quantity FROM invoice_items "
            "WHERE invoice_id=?", (inv_id,)).fetchall()
        for it in items:
            if it["product_code"] == COMMISSION_CODE:
                continue
            conn.execute(
                "UPDATE products SET stock_qty=stock_qty+? WHERE code=?",
                (int(it["quantity"]), it["product_code"]))
        if inv["customer_code"] != QUICK_CUSTOMER_CODE:
            earned = int(inv["total_items"]) * POINTS_PER_PIECE
            used = int(inv["loyalty_points_used"] or 0)
            net = earned - used
            if inv["customer_id"] and net != 0:
                conn.execute(
                    "UPDATE customers SET loyalty_points=loyalty_points-? "
                    "WHERE id=?", (net, inv["customer_id"]))
                conn.execute(
                    "INSERT INTO loyalty_log (customer_id, change_amount, "
                    "reason, performed_by) VALUES (?, ?, ?, ?)",
                    (inv["customer_id"], -net,
                     f"تراجع عن فاتورة #{inv['invoice_number']}",
                     performed_by or "system"))
        conn.execute("DELETE FROM invoice_items WHERE invoice_id=?", (inv_id,))
        conn.execute("DELETE FROM invoices WHERE id=?", (inv_id,))
    return True


def get_invoices(search="", status=None, date_from=None, date_to=None):
    q = "SELECT * FROM invoices"
    cl, ps = [], []
    if status:
        cl.append("status=?"); ps.append(status)
    if search:
        t = f"%{search.strip()}%"
        cl.append(
            "(customer_name LIKE ? OR customer_phone LIKE ? "
            "OR customer_code LIKE ? OR CAST(invoice_number AS TEXT) LIKE ?)")
        ps += [t, t, t, t]
    dc, dp = _date_filter("created_at", date_from, date_to)
    cl += dc; ps += dp
    if cl:
        q += " WHERE " + " AND ".join(cl)
    q += " ORDER BY id DESC LIMIT " + str(SOFT_LIMIT)
    with get_connection() as conn:
        return _rows_to_dicts(conn.execute(q, ps).fetchall())


def get_pending_shipping():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM invoices WHERE status='paid' "
            "AND (waybill_number IS NULL OR waybill_number='') "
            "ORDER BY id DESC LIMIT " + str(SOFT_LIMIT)).fetchall()
    return _rows_to_dicts(rows)


def get_shipped():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM invoices WHERE status='paid' "
            "AND waybill_number IS NOT NULL AND waybill_number<>'' "
            "ORDER BY id DESC LIMIT " + str(SOFT_LIMIT)).fetchall()
    return _rows_to_dicts(rows)


# --- returns ---
def _next_return_number(conn):
    m = conn.execute(
        "SELECT COALESCE(MAX(return_number), 0) AS m FROM returns").fetchone()
    return int(m["m"]) + 1


def create_return(invoice_id, items, notes="", created_by=""):
    """
    items: list of dicts, each with:
      - product_code : str
      - product_name : str
      - quantity     : int
      - price        : float  (invoice price)
      - reason_type  : 'defect' | 'normal'

    Stock impact per item:
      - normal → products.stock_qty += qty   (sellable)
      - defect → products.defect_qty += qty  (sent back to factory)

    Financial impact:
      - returns.total_refund accumulates (deducted from revenue by
        get_profit_report via get_returns_total).
      - returns.reason_type (summary) = 'defect' if any item is defect
        else 'normal'.
      - returns.return_code auto-generated as R0001, R0002, ...
    """
    items = list(items or [])
    if not items:
        raise ValueError("لا أصناف في المرتجع.")

    with get_connection() as conn:
        inv = conn.execute(
            "SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
        if inv is None:
            raise ValueError("الفاتورة غير موجودة.")

        sold = {r["product_code"]: int(r["q"])
                for r in conn.execute(
                    "SELECT product_code, SUM(quantity) AS q "
                    "FROM invoice_items WHERE invoice_id=? "
                    "GROUP BY product_code", (invoice_id,)).fetchall()}

        returned = {r["product_code"]: int(r["q"])
                    for r in conn.execute(
                        "SELECT ri.product_code, SUM(ri.quantity) AS q "
                        "FROM return_items ri "
                        "JOIN returns r ON r.id = ri.return_id "
                        "WHERE r.invoice_id=? "
                        "GROUP BY ri.product_code", (invoice_id,)).fetchall()}

        lines = []
        total_refund = 0.0
        per_code = {}
        for raw in items:
            code = str(raw.get("product_code") or "").strip()
            qty = int(raw.get("quantity", 0) or 0)
            reason = raw.get("reason_type", RETURN_REASON_NORMAL)
            if reason not in (RETURN_REASON_DEFECT, RETURN_REASON_NORMAL):
                raise ValueError(f"نوع مرتجع غير صالح للصنف {code}.")
            if qty <= 0:
                continue
            if code not in sold:
                raise ValueError(f"'{code}' ليس في هذه الفاتورة.")
            per_code[code] = per_code.get(code, 0) + qty
            price_row = conn.execute(
                "SELECT price FROM invoice_items WHERE invoice_id=? "
                "AND product_code=? LIMIT 1",
                (invoice_id, code)).fetchone()
            price = _money(price_row["price"] if price_row else 0)
            lines.append({
                "product_code": code,
                "product_name": raw.get("product_name") or code,
                "quantity": qty,
                "price": price,
                "total_price": _money(price * qty),
                "reason_type": reason,
            })
            total_refund += price * qty

        if not lines:
            raise ValueError("لم يتم تحديد كميات صالحة للإرجاع.")

        for code, q in per_code.items():
            available = sold[code] - returned.get(code, 0)
            if q > available:
                raise ValueError(
                    f"مجموع المرتجع من '{code}' ({q}) يتجاوز المتاح "
                    f"({available}).")

        has_defect = any(l["reason_type"] == RETURN_REASON_DEFECT
                         for l in lines)
        summary_reason = (RETURN_REASON_DEFECT if has_defect
                          else RETURN_REASON_NORMAL)

        ret_num = _next_return_number(conn)
        ret_code = _next_return_code(conn)
        cur = conn.execute(
            """INSERT INTO returns
               (return_number, return_code, invoice_id, invoice_number,
                customer_id, customer_name, reason_type, notes, total_refund,
                created_by, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ret_num, ret_code, invoice_id, int(inv["invoice_number"] or 0),
             inv["customer_id"], inv["customer_name"] or "",
             summary_reason, (notes or "").strip(),
             _money(total_refund), created_by or "system", _now()))
        rid = int(cur.lastrowid)

        for l in lines:
            conn.execute(
                """INSERT INTO return_items
                   (return_id, product_code, product_name, quantity,
                    price, total_price, reason_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (rid, l["product_code"], l["product_name"],
                 l["quantity"], l["price"], l["total_price"],
                 l["reason_type"]))
            if l["reason_type"] == RETURN_REASON_NORMAL:
                conn.execute(
                    "UPDATE products SET stock_qty=stock_qty+? WHERE code=?",
                    (l["quantity"], l["product_code"]))
            else:  # defect → not sellable, sent back to factory
                conn.execute(
                    "UPDATE products SET defect_qty=defect_qty+? WHERE code=?",
                    (l["quantity"], l["product_code"]))

    return get_return(rid)


def update_return(ret_id, notes=None, per_item_reasons=None,
                  performed_by=""):
    """
    Edit an existing return:
      - notes: new notes string (optional)
      - per_item_reasons: dict {product_code: new_reason} (optional).
        When a reason changes, stock impact is *reversed* on the old bucket
        and *applied* on the new one:
          normal → stock_qty, defect → defect_qty
      - the header summary reason_type is recomputed as 'defect' if any
        item is defect else 'normal'.
    """
    per_item_reasons = dict(per_item_reasons or {})
    with get_connection() as conn:
        ret = conn.execute("SELECT * FROM returns WHERE id=?",
                           (ret_id,)).fetchone()
        if ret is None:
            return False
        items = conn.execute(
            "SELECT * FROM return_items WHERE return_id=?",
            (ret_id,)).fetchall()
        for it in items:
            code = it["product_code"]
            old_reason = it.get("reason_type") or RETURN_REASON_NORMAL
            new_reason = per_item_reasons.get(code, old_reason)
            if new_reason not in (RETURN_REASON_DEFECT, RETURN_REASON_NORMAL):
                raise ValueError(f"نوع مرتجع غير صالح للصنف {code}.")
            if new_reason == old_reason:
                continue
            qty = int(it["quantity"])
            if (old_reason == RETURN_REASON_NORMAL
                    and new_reason == RETURN_REASON_DEFECT):
                conn.execute(
                    "UPDATE products SET stock_qty=stock_qty-? WHERE code=?",
                    (qty, code))
                conn.execute(
                    "UPDATE products SET defect_qty=defect_qty+? WHERE code=?",
                    (qty, code))
            elif (old_reason == RETURN_REASON_DEFECT
                  and new_reason == RETURN_REASON_NORMAL):
                conn.execute(
                    "UPDATE products SET defect_qty=defect_qty-? WHERE code=?",
                    (qty, code))
                conn.execute(
                    "UPDATE products SET stock_qty=stock_qty+? WHERE code=?",
                    (qty, code))
            conn.execute(
                "UPDATE return_items SET reason_type=? WHERE id=?",
                (new_reason, it["id"]))
        # Recompute summary
        has_defect = conn.execute(
            "SELECT 1 FROM return_items WHERE return_id=? "
            "AND reason_type='defect' LIMIT 1", (ret_id,)).fetchone() is not None
        summary = RETURN_REASON_DEFECT if has_defect else RETURN_REASON_NORMAL
        fields, params = ["reason_type=?"], [summary]
        if notes is not None:
            fields.append("notes=?"); params.append(notes.strip())
        params.append(ret_id)
        conn.execute(f"UPDATE returns SET {', '.join(fields)} WHERE id=?",
                     params)
    return True


def delete_return(ret_id, performed_by=""):
    """Reverse stock impact per item (based on its reason), then delete."""
    with get_connection() as conn:
        ret = conn.execute("SELECT * FROM returns WHERE id=?",
                           (ret_id,)).fetchone()
        if ret is None:
            return False
        items = conn.execute(
            "SELECT * FROM return_items WHERE return_id=?",
            (ret_id,)).fetchall()
        for it in items:
            qty = int(it["quantity"])
            reason = it.get("reason_type") or RETURN_REASON_NORMAL
            if reason == RETURN_REASON_NORMAL:
                conn.execute(
                    "UPDATE products SET stock_qty=stock_qty-? WHERE code=?",
                    (qty, it["product_code"]))
            else:
                conn.execute(
                    "UPDATE products SET defect_qty=defect_qty-? WHERE code=?",
                    (qty, it["product_code"]))
        conn.execute("DELETE FROM return_items WHERE return_id=?", (ret_id,))
        conn.execute("DELETE FROM returns WHERE id=?", (ret_id,))
    return True


def get_return(rid):
    with get_connection() as conn:
        h = conn.execute("SELECT * FROM returns WHERE id=?", (rid,)).fetchone()
        if h is None:
            return None
        items = conn.execute(
            "SELECT * FROM return_items WHERE return_id=? ORDER BY id",
            (rid,)).fetchall()
    r = dict(h)
    r["items"] = _rows_to_dicts(items)
    return r


def get_returns(date_from=None, date_to=None, invoice_number=None):
    q = "SELECT * FROM returns"
    cl, ps = [], []
    dc, dp = _date_filter("created_at", date_from, date_to)
    cl += dc; ps += dp
    if invoice_number is not None:
        try:
            cl.append("invoice_number=?"); ps.append(int(invoice_number))
        except (TypeError, ValueError):
            pass
    if cl:
        q += " WHERE " + " AND ".join(cl)
    q += " ORDER BY id DESC LIMIT " + str(SOFT_LIMIT)
    with get_connection() as conn:
        return _rows_to_dicts(conn.execute(q, ps).fetchall())


def get_return_items_for_invoice(invoice_id):
    """Return eligible products for return with remaining quantities."""
    with get_connection() as conn:
        sold = conn.execute(
            "SELECT product_code, MAX(product_name) AS name, "
            "       SUM(quantity) AS q, AVG(price) AS p "
            "FROM invoice_items WHERE invoice_id=? GROUP BY product_code",
            (invoice_id,)).fetchall()
        returned = {}
        for r in conn.execute(
                "SELECT ri.product_code, SUM(ri.quantity) AS q "
                "FROM return_items ri JOIN returns r ON r.id = ri.return_id "
                "WHERE r.invoice_id=? GROUP BY ri.product_code",
                (invoice_id,)).fetchall():
            returned[r["product_code"]] = int(r["q"])
    out = []
    for s in sold:
        remaining = int(s["q"]) - returned.get(s["product_code"], 0)
        if remaining <= 0:
            continue
        out.append({
            "product_code": s["product_code"],
            "product_name": s["name"],
            "remaining": remaining,
            "price": _money(s["p"]),
        })
    return out


# --- expenses ---
def add_expense(category, amount, notes="", expense_date=None):
    cat = (category or "").strip()
    if not cat:
        raise ValueError("الفئة مطلوبة.")
    amt = _money(amount)
    if amt <= 0:
        raise ValueError("المبلغ يجب أن يكون > 0.")
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO expenses (category, amount, notes, date) "
            "VALUES (?, ?, ?, ?)",
            (cat, amt, notes.strip(), expense_date or _today()))
        return int(cur.lastrowid)


def update_expense(eid, category, amount, notes="", expense_date=None):
    cat = (category or "").strip()
    if not cat:
        raise ValueError("الفئة مطلوبة.")
    amt = _money(amount)
    if amt <= 0:
        raise ValueError("المبلغ يجب أن يكون > 0.")
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE expenses SET category=?, amount=?, notes=?, date=? "
            "WHERE id=?",
            (cat, amt, notes.strip(), expense_date or _today(), eid))
    return cur.rowcount > 0


def delete_expense(eid):
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM expenses WHERE id=?", (eid,))
    return cur.rowcount > 0


def get_expenses(category="", date_from=None, date_to=None):
    q = "SELECT * FROM expenses"
    cl, ps = [], []
    if category:
        cl.append("category=?"); ps.append(category)
    dc, dp = _date_filter("date", date_from, date_to)
    cl += dc; ps += dp
    if cl:
        q += " WHERE " + " AND ".join(cl)
    q += " ORDER BY date DESC, id DESC LIMIT " + str(SOFT_LIMIT)
    with get_connection() as conn:
        return _rows_to_dicts(conn.execute(q, ps).fetchall())


def get_expense_categories():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT category FROM expenses WHERE TRIM(category)<>'' "
            "ORDER BY category COLLATE NOCASE").fetchall()
    return [r["category"] for r in rows]


def get_total_expenses(date_from=None, date_to=None):
    cl, ps = _date_filter("date", date_from, date_to)
    q = "SELECT COALESCE(SUM(amount), 0) AS t FROM expenses"
    if cl:
        q += " WHERE " + " AND ".join(cl)
    with get_connection() as conn:
        return _money(conn.execute(q, ps).fetchone()["t"])


# --- purchases ---
def create_purchase(code, qty, pp, sp, supplier=None):
    code = (code or "").strip()
    p = get_product_by_code(code)
    if p is None:
        raise ValueError("المنتج غير موجود.")
    qty = int(qty or 0)
    if qty <= 0:
        raise ValueError("الكمية > 0.")
    pp = _money(pp); sp = _money(sp)
    if pp < 0 or sp < 0:
        raise ValueError("أسعار سالبة.")
    tc = _money(pp * qty)
    supplier_val = (supplier or "").strip() or p.get("supplier", "")
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO purchases (product_code, product_name, supplier, "
            "quantity, purchase_price, selling_price, total_cost) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (code, p["name"], supplier_val, qty, pp, sp, tc))
        pid = int(cur.lastrowid)
        conn.execute(
            "UPDATE products SET stock_qty=stock_qty+?, cost_price=?, "
            "wholesale_price=? WHERE code=?", (qty, pp, sp, code))
    return pid


def update_purchase(pid, code, qty, pp, sp, supplier=None):
    old = get_purchase_by_id(pid)
    if old is None:
        return False
    code = (code or "").strip()
    p = get_product_by_code(code)
    if p is None:
        raise ValueError("المنتج غير موجود.")
    qty = int(qty or 0)
    if qty <= 0:
        raise ValueError("الكمية > 0.")
    pp = _money(pp); sp = _money(sp)
    if pp < 0 or sp < 0:
        raise ValueError("أسعار سالبة.")
    tc = _money(pp * qty)
    supplier_val = (supplier or "").strip() or p.get("supplier", "")
    with get_connection() as conn:
        conn.execute("UPDATE products SET stock_qty=stock_qty-? WHERE code=?",
                     (int(old["quantity"]), old["product_code"]))
        conn.execute(
            "UPDATE products SET stock_qty=stock_qty+?, cost_price=?, "
            "wholesale_price=? WHERE code=?", (qty, pp, sp, code))
        cur = conn.execute(
            "UPDATE purchases SET product_code=?, product_name=?, supplier=?, "
            "quantity=?, purchase_price=?, selling_price=?, total_cost=? "
            "WHERE id=?",
            (code, p["name"], supplier_val, qty, pp, sp, tc, pid))
    return cur.rowcount > 0


def delete_purchase(pid):
    old = get_purchase_by_id(pid)
    if old is None:
        return False
    with get_connection() as conn:
        conn.execute("UPDATE products SET stock_qty=stock_qty-? WHERE code=?",
                     (int(old["quantity"]), old["product_code"]))
        cur = conn.execute("DELETE FROM purchases WHERE id=?", (pid,))
    return cur.rowcount > 0


def get_purchase_by_id(pid):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM purchases WHERE id=?", (pid,)).fetchone()
    return _row_to_dict(row)


def get_all_purchases(search="", date_from=None, date_to=None):
    q = "SELECT * FROM purchases"
    cl, ps = [], []
    if search:
        t = f"%{search.strip()}%"
        cl.append("(product_name LIKE ? OR product_code LIKE ? "
                  "OR supplier LIKE ?)")
        ps += [t, t, t]
    dc, dp = _date_filter("created_at", date_from, date_to)
    cl += dc; ps += dp
    if cl:
        q += " WHERE " + " AND ".join(cl)
    q += " ORDER BY id DESC LIMIT " + str(SOFT_LIMIT)
    with get_connection() as conn:
        return _rows_to_dicts(conn.execute(q, ps).fetchall())


def get_purchases_in_range(date_from=None, date_to=None, limit=2000):
    q = "SELECT * FROM purchases"
    cl, ps = _date_filter("created_at", date_from, date_to)
    if cl:
        q += " WHERE " + " AND ".join(cl)
    q += " ORDER BY id DESC LIMIT ?"
    ps.append(int(limit))
    with get_connection() as conn:
        return _rows_to_dicts(conn.execute(q, ps).fetchall())


# --- reports ---
def get_sales_summary(date_from=None, date_to=None):
    cl, ps = _date_filter("created_at", date_from, date_to)
    cl.append("status = 'paid'")
    q = """SELECT COUNT(*) AS c,
                  COALESCE(SUM(total_items), 0) AS ti,
                  COALESCE(SUM(subtotal), 0) AS st,
                  COALESCE(SUM(discount), 0) AS ds,
                  COALESCE(SUM(net_total), 0) AS nt
           FROM invoices"""
    if cl:
        q += " WHERE " + " AND ".join(cl)
    with get_connection() as conn:
        r = conn.execute(q, ps).fetchone()
    return {"invoice_count": int(r["c"]),
            "total_items": int(r["ti"]),
            "subtotal": _money(r["st"]),
            "discount": _money(r["ds"]),
            "net_total": _money(r["nt"])}


def get_returns_total(date_from=None, date_to=None):
    cl, ps = _date_filter("created_at", date_from, date_to)
    q = "SELECT COALESCE(SUM(total_refund), 0) AS t FROM returns"
    if cl:
        q += " WHERE " + " AND ".join(cl)
    with get_connection() as conn:
        return _money(conn.execute(q, ps).fetchone()["t"])


def get_cost_of_goods_sold(date_from=None, date_to=None):
    cl, ps = _date_filter("i.created_at", date_from, date_to)
    cl.append("i.status = 'paid'")
    q = """SELECT COALESCE(SUM(ii.quantity * COALESCE(p.cost_price, 0)), 0) AS c
           FROM invoice_items ii
           JOIN invoices i ON i.id = ii.invoice_id
           LEFT JOIN products p ON p.code = ii.product_code"""
    q += " WHERE " + " AND ".join(cl)
    with get_connection() as conn:
        return _money(conn.execute(q, ps).fetchone()["c"])


def get_profit_report(date_from=None, date_to=None):
    s = get_sales_summary(date_from, date_to)
    cogs = get_cost_of_goods_sold(date_from, date_to)
    exp = get_total_expenses(date_from, date_to)
    returns_total = get_returns_total(date_from, date_to)
    rev = _money(s["net_total"])
    net_rev = _money(rev - returns_total)
    gross = _money(net_rev - cogs)
    net = _money(gross - exp)
    return {"revenue": rev, "returns": returns_total,
            "net_revenue": net_rev, "cogs": cogs,
            "gross_profit": gross, "expenses": exp,
            "net_profit": net,
            "invoice_count": s["invoice_count"],
            "total_items": s["total_items"]}


def get_dashboard_stats():
    with get_connection() as conn:
        def sc(q, p=()):
            r = conn.execute(q, p).fetchone()
            return r[0] if r is not None else 0
        return {
            "total_products": int(sc("SELECT COUNT(*) FROM products")),
            "total_customers": int(sc(
                "SELECT COUNT(*) FROM customers WHERE code<>?",
                (QUICK_CUSTOMER_CODE,))),
            "today_sales": _money(sc(
                "SELECT COALESCE(SUM(net_total), 0) FROM invoices "
                "WHERE date(created_at) = date('now','localtime') "
                "AND status = 'paid'")),
            "today_invoices": int(sc(
                "SELECT COUNT(*) FROM invoices "
                "WHERE date(created_at) = date('now','localtime') "
                "AND status = 'paid'")),
            "pending_invoices": int(sc(
                "SELECT COUNT(*) FROM invoices WHERE status = 'pending'")),
            "pending_shipping": int(sc(
                "SELECT COUNT(*) FROM invoices WHERE status = 'paid' "
                "AND (waybill_number IS NULL OR waybill_number = '')")),
            "month_sales": _money(sc(
                "SELECT COALESCE(SUM(net_total), 0) FROM invoices "
                "WHERE strftime('%Y-%m', created_at) = "
                "strftime('%Y-%m','now','localtime') AND status = 'paid'")),
            "month_expenses": _money(sc(
                "SELECT COALESCE(SUM(amount), 0) FROM expenses "
                "WHERE strftime('%Y-%m', date) = "
                "strftime('%Y-%m','now','localtime')")),
        }


# --- settings ---
def get_setting(k, default=None):
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?",
                           (k,)).fetchone()
    return default if row is None else row["value"]


def set_settings(values):
    with get_connection() as conn:
        for k, v in values.items():
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (k, "" if v is None else str(v)))


def get_all_settings():
    with get_connection() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    s = dict(DEFAULT_SETTINGS)
    s.update({r["key"]: r["value"] for r in rows})
    return s


def get_currency_symbol():
    return get_setting("currency_symbol",
                       DEFAULT_SETTINGS["currency_symbol"]) or "ج.م"


def get_invoice_footer():
    return get_setting("invoice_footer",
                       DEFAULT_SETTINGS["invoice_footer"]) or ""


def money_str(v, cur=None):
    if cur is None:
        cur = get_currency_symbol()
    try:
        return f"{float(v):,.2f} {cur}"
    except (TypeError, ValueError):
        return f"0.00 {cur}"


def backup_database(dest=None):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    if dest is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = os.path.join(BACKUP_DIR, f"sierra_backup_{ts}.db")
    dest = os.path.abspath(dest)
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    with get_connection() as src:
        tgt = sqlite3.connect(dest)
        try:
            src.backup(tgt)
        finally:
            tgt.close()
    return dest


def restore_database_from(bpath):
    bpath = os.path.abspath(bpath)
    if not os.path.isfile(bpath):
        raise FileNotFoundError(bpath)
    with open(bpath, "rb") as f:
        if f.read(16) != b"SQLite format 3\x00":
            raise ValueError("ليس ملف SQLite صالح.")
    try:
        with get_connection() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    except Exception:
        pass
    for suf in ("-wal", "-shm"):
        sc = DB_PATH + suf
        try:
            if os.path.exists(sc):
                os.remove(sc)
        except Exception:
            pass
    shutil.copy2(bpath, DB_PATH)
    return DB_PATH


def clear_all_business_data():
    """Wipe all business data, keep users/settings, recreate quick customer."""
    with get_connection() as conn:
        for tbl in ("return_items", "returns", "invoice_items", "invoices",
                    "loyalty_log", "purchases", "expenses", "products",
                    "suppliers", "customers"):
            try:
                conn.execute(f"DELETE FROM {tbl}")
            except Exception:
                pass
        try:
            conn.execute(
                "DELETE FROM sqlite_sequence WHERE name IN "
                "('products','customers','suppliers','invoices',"
                "'invoice_items','purchases','expenses','loyalty_log',"
                "'returns','return_items')")
        except Exception:
            pass
        _ensure_quick_customer(conn)


# ===========================================================================
# FILE PICKER HELPERS
# ===========================================================================
def _attach_picker(page, picker):
    try:
        if hasattr(page, "services"):
            page.services.append(picker)
        elif hasattr(page, "overlay"):
            page.overlay.append(picker)
        page.update()
    except Exception:
        pass


def _detach_picker(page, picker):
    for attr in ("services", "overlay"):
        try:
            lst = getattr(page, attr, None)
            if lst is not None and picker in lst:
                lst.remove(picker)
        except Exception:
            pass
    try:
        page.update()
    except Exception:
        pass


def _extract_path(e):
    if e is None:
        return None
    p = getattr(e, "path", None)
    if p:
        return p
    files = getattr(e, "files", None)
    if files:
        try:
            fp = getattr(files[0], "path", None)
            if fp:
                return fp
        except Exception:
            return None
    return None


# ===========================================================================
# VIEWS
# ===========================================================================
class LoginView:
    def __init__(self, app, page):
        self.app = app
        self.page = page
        self.username = text_field("اسم المستخدم", autofocus=True,
                                   prefix_icon=ft.icons.PERSON_OUTLINE,
                                   width=360)
        self.password = text_field("كلمة المرور", password=True,
                                   prefix_icon=ft.icons.LOCK_OUTLINE,
                                   width=360, on_submit=self._login)
        self.error = ft.Text("", color=DANGER, size=FS_SMALL, visible=False)
        self.btn = primary_button("تسجيل الدخول", self._login,
                                  icon=ft.icons.LOGIN, width=360, height=48)

    def _login(self, e=None):
        self.error.visible = False
        try:
            self.error.update()
        except Exception:
            pass
        u = authenticate(self.username.value or "", self.password.value or "")
        if u is None:
            self.error.value = "بيانات غير صحيحة."
            self.error.visible = True
            self.error.update()
            return
        self.app.on_login_success(u)

    def build(self):
        logo_path = get_setting("login_logo_path", "") or ""
        if logo_path and os.path.exists(logo_path):
            logo_widget = ft.Container(
                content=ft.Image(src=logo_path, width=90, height=90,
                                 fit=ft.ImageFit.CONTAIN),
                width=100, height=100, alignment=ft.alignment.center)
        else:
            logo_widget = ft.Container(
                content=ft.Icon(ft.icons.STOREFRONT, size=34, color=BG_BLACK),
                width=72, height=72, bgcolor=ACCENT,
                border_radius=RADIUS_LG, alignment=ft.alignment.center)

        brand = ft.Column([
            logo_widget,
            ft.Text("SIERRA STORE", color=TEXT_PRIMARY, size=34,
                    weight=ft.FontWeight.W_900),
            ft.Text("سييرا ستور — نظام إدارة متجر الملابس",
                    color=TEXT_MUTED, size=FS_BODY),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=SP_SM)

        inner_col = ft.Column([
            ft.Text("مرحباً بعودتك", color=TEXT_PRIMARY, size=20,
                    weight=ft.FontWeight.W_700,
                    text_align=ft.TextAlign.CENTER),
            ft.Text("سجّل الدخول", color=TEXT_MUTED, size=FS_SMALL,
                    text_align=ft.TextAlign.CENTER),
            ft.Container(height=SP_MD),
            ft.Row([self.username], alignment=ft.MainAxisAlignment.CENTER),
            ft.Row([self.password], alignment=ft.MainAxisAlignment.CENTER),
            ft.Row([self.error], alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(height=SP_SM),
            ft.Row([self.btn], alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(height=SP_SM),
            ft.Row([ft.Text("الافتراضي: admin / admin123",
                            color=TEXT_MUTED, size=FS_TINY)],
                   alignment=ft.MainAxisAlignment.CENTER),
        ], spacing=SP_SM, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        box = card(inner_col, padding=SP_XL, hover=True)

        return ft.Container(
            content=ft.Column([brand, ft.Container(height=SP_LG), box],
                              horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                              alignment=ft.MainAxisAlignment.CENTER,
                              spacing=0),
            alignment=ft.alignment.center, expand=True, bgcolor=BG_BLACK,
            padding=SP_LG)


class DashboardView:
    def __init__(self, app, page, user):
        self.app = app; self.page = page; self.user = user
        self.currency = get_currency_symbol()

    def build(self):
        st = get_dashboard_stats()
        rep = get_profit_report()
        net_profit = rep["net_profit"]
        tiles = [
            ("مبيعات اليوم (مدفوع)", money_str(st["today_sales"], self.currency), SUCCESS),
            ("فواتير اليوم (مدفوع)", str(st["today_invoices"]), TEXT_PRIMARY),
            ("قيد الدفع", str(st["pending_invoices"]), WARNING),
            ("قيد الشحن", str(st["pending_shipping"]), WARNING),
            ("مبيعات الشهر", money_str(st["month_sales"], self.currency), TEXT_PRIMARY),
            ("مصروفات الشهر", money_str(st["month_expenses"], self.currency), WARNING),
            ("صافي الأرباح (الفترة)", money_str(net_profit, self.currency),
             SUCCESS if net_profit >= 0 else DANGER),
            ("المنتجات", str(st["total_products"]), TEXT_PRIMARY),
            ("العملاء", str(st["total_customers"]), TEXT_PRIMARY),
        ]
        grid = ft.Row(wrap=True, spacing=SP_MD, run_spacing=SP_MD, expand=True)
        for label, val, color in tiles:
            grid.controls.append(ft.Container(
                content=ft.Column([
                    ft.Text(label.upper(), color=TEXT_MUTED, size=FS_TINY,
                            weight=ft.FontWeight.W_700),
                    ft.Text(val, color=color, size=18,
                            weight=ft.FontWeight.W_800),
                ], spacing=4, tight=True),
                padding=SP_MD, bgcolor=BG_CARD,
                border=ft.border.all(1, BORDER),
                border_radius=RADIUS_MD, width=250, height=90,
                on_hover=_hv_card))
        return ft.Column([
            ft.Row([page_title("لوحة التحكم",
                               f"أهلاً {self.user['username']}"),
                    ft.Container(expand=True)]),
            ft.Container(height=SP_SM), grid,
        ], spacing=0, expand=True)


# --------------------------- CUSTOMERS ---------------------------
class CustomersView:
    def __init__(self, app, page, user):
        self.app = app; self.page = page; self.user = user
        self.search = text_field("بحث فوري…", prefix_icon=ft.icons.SEARCH,
                                 on_change=lambda e: self._refresh(),
                                 width=300)
        self.table = ft.Container(expand=True)

    def build(self):
        header = ft.Row([
            page_title("العملاء", "'1003' يطابق 'SF-1003'"),
            ft.Container(expand=True), self.search,
            primary_button("إضافة عميل", self._add_dialog,
                           icon=ft.icons.ADD, width=170),
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=SP_MD)
        self._refresh()
        return ft.Column([
            header, ft.Container(height=SP_SM),
            card(ft.Column([self.table], expand=True, spacing=0),
                 padding=0, hover=False, expand=True),
        ], spacing=0, expand=True)

    def _refresh(self):
        customers = [c for c in flexible_customer_search(self.search.value or "")
                     if c.get("code") != QUICK_CUSTOMER_CODE]
        rows = []
        for c in customers:
            rows.append([
                ft.Text(c["code"], color=SUCCESS, size=FS_SMALL,
                        weight=ft.FontWeight.W_700, max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(c["name"], color=TEXT_PRIMARY, size=FS_SMALL,
                        weight=ft.FontWeight.W_600, max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(c["phone"] or "—", color=TEXT_SECONDARY, size=FS_SMALL,
                        max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(c["address"] or "—", color=TEXT_SECONDARY, size=FS_SMALL,
                        max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(c["governorate"] or "—", color=TEXT_SECONDARY,
                        size=FS_SMALL, max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS),
                chip(f"{c['loyalty_points']}", color=WARNING),
            ])

        def row_actions(c):
            return [
                {"label": "تعديل", "icon": ft.icons.EDIT,
                 "handler": lambda c=c: self._edit_dialog(c)},
                {"label": "طباعة A4", "icon": ft.icons.PRINT,
                 "handler": lambda c=c: self._print(c)},
                {"label": "حذف", "icon": ft.icons.DELETE,
                 "handler": lambda c=c: self._confirm_delete(c),
                 "danger": True},
            ]

        self.table.content = data_table(
            self.page,
            [("الكود", 70), ("الاسم", 120), ("الهاتف", 85),
             ("العنوان", 120), ("المحافظة", 70), ("النقاط", 60)],
            rows, "لا عملاء.", raw_data=customers,
            row_actions_builder=row_actions)
        try:
            self.table.update()
        except Exception:
            pass

    def _add_dialog(self, e=None): self._form(None)
    def _edit_dialog(self, c): self._form(c)

    def _form(self, c):
        is_edit = c is not None
        name = text_field("الاسم *", value=c["name"] if is_edit else "", width=400)
        phone = text_field("الهاتف", value=c["phone"] if is_edit else "", width=220)
        address = text_field("العنوان", value=c["address"] if is_edit else "",
                             width=400)
        gov = text_field("المحافظة", value=c["governorate"] if is_edit else "",
                         width=220)
        error = ft.Text("", color=DANGER, size=FS_SMALL, visible=False)

        def save(e):
            error.visible = False
            try:
                if is_edit:
                    update_customer(c["id"], name.value, phone.value,
                                    address.value, gov.value)
                else:
                    _, code = add_customer(name.value, phone.value,
                                           address.value, gov.value)
                    snack(self.page, f"تم إنشاء {code}", kind="success")
            except Exception as ex:
                error.value = str(ex); error.visible = True
                error.update(); return
            self.page.close(dlg); self._refresh()

        def cancel(e=None): self.page.close(dlg)

        dlg = ft.AlertDialog(
            modal=True, bgcolor=BG_CARD,
            title=ft.Text("تعديل عميل" if is_edit else "إضافة عميل",
                          color=TEXT_PRIMARY, weight=ft.FontWeight.W_700,
                          size=FS_SECTION),
            content=ft.Column([name, ft.Row([phone, gov], spacing=SP_MD),
                               address, error], spacing=SP_SM, width=470),
            actions=[ghost_button("إلغاء", cancel, width=110),
                     primary_button("حفظ", save, icon=ft.icons.CHECK,
                                    width=110)])
        self.page.open(dlg)

    def _print(self, c):
        pairs = [
            ("كود العميل", c["code"]), ("الاسم", c["name"]),
            ("الهاتف", c.get("phone") or "—"),
            ("العنوان", c.get("address") or "—"),
            ("المحافظة", c.get("governorate") or "—"),
            ("نقاط الولاء", c["loyalty_points"]),
            ("تاريخ التسجيل", c["created_at"][:16]),
        ]
        open_report_preview(
            self.page, "بطاقة عميل", ["البند", "القيمة"],
            [[k, v] for k, v in pairs], [],
            "customers", f"customer_{c['code']}")

    def _confirm_delete(self, c):
        def do():
            try:
                delete_customer(c["id"]); self._refresh()
                snack(self.page, f"تم حذف '{c['name']}'.", kind="success")
            except Exception as ex:
                snack(self.page, str(ex), kind="error")
        confirm_dialog(self.page, "حذف العميل", f"حذف '{c['name']}'؟",
                       do, confirm_text="حذف", danger=True)


# --------------------------- LOYALTY ---------------------------
class LoyaltyView:
    def __init__(self, app, page, user):
        self.app = app; self.page = page; self.user = user
        self.search = text_field(
            "بحث (اسم / هاتف / رقم مثل 1003)",
            prefix_icon=ft.icons.SEARCH,
            on_submit=lambda e: self._search(),
            on_change=lambda e: self._search(), width=360)
        self.results = ft.Container(expand=True)
        self._search()

    def build(self):
        return ft.Column([
            ft.Row([
                page_title("نقاط الولاء", "اضغط صف لعرض تفاصيله"),
                ft.Container(expand=True), self.search,
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=SP_MD),
            ft.Container(height=SP_SM),
            card(ft.Column([self.results], expand=True, spacing=0),
                 padding=SP_MD, hover=False, expand=True),
        ], spacing=0, expand=True)

    def _search(self):
        term = (self.search.value or "").strip()
        customers = (flexible_customer_search(term)
                     if term else get_all_customers()[:50])
        customers = [c for c in customers
                     if c.get("code") != QUICK_CUSTOMER_CODE]
        if not customers:
            self.results.content = empty_state(
                "لا نتائج.", icon=ft.icons.PERSON_OFF)
        else:
            rows = []
            for c in customers:
                rows.append([
                    ft.Text(c["code"], color=SUCCESS, size=FS_SMALL,
                            weight=ft.FontWeight.W_700, max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(c["name"], color=TEXT_PRIMARY, size=FS_SMALL,
                            weight=ft.FontWeight.W_600, max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(c["phone"] or "—", color=TEXT_SECONDARY,
                            size=FS_SMALL, max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(c["address"] or "—", color=TEXT_SECONDARY,
                            size=FS_SMALL, max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS),
                    chip(f"{c['loyalty_points']}", color=WARNING),
                ])
            self.results.content = data_table(
                self.page,
                [("الكود", 80), ("الاسم", 150), ("الهاتف", 100),
                 ("العنوان", 150), ("النقاط", 80)],
                rows, "لا عملاء.", raw_data=customers,
                on_row_click=lambda c: self._open_details(c))
        try:
            self.results.update()
        except Exception:
            pass

    def _open_details(self, cust):
        cust = get_customer_by_id(cust["id"]) or cust
        log = get_loyalty_log(cust["id"], limit=200)
        points_display = ft.Text(str(cust["loyalty_points"]),
                                 color=WARNING, size=26,
                                 weight=ft.FontWeight.W_900)

        def render_history(records):
            if not records:
                return empty_state("لا حركات.", icon=ft.icons.RECEIPT)
            rows = []
            for r in records:
                rows.append([
                    ft.Text(r["created_at"][:16], color=TEXT_SECONDARY,
                            size=FS_TINY, max_lines=1),
                    ft.Text(f"{r['change_amount']:+d}",
                            color=(SUCCESS if r["change_amount"] > 0
                                   else DANGER),
                            size=FS_SMALL, weight=ft.FontWeight.W_700),
                    ft.Text(r["reason"] or "—", color=TEXT_MUTED,
                            size=FS_TINY, max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(r.get("performed_by") or "system",
                            color=INFO, size=FS_TINY,
                            weight=ft.FontWeight.W_600, max_lines=1),
                ])
            return data_table(
                self.page,
                [("التاريخ", 130), ("النقاط", 90),
                 ("السبب", 240), ("بواسطة", 130)],
                rows, "لا حركات.")

        history_holder = ft.Container(content=render_history(log))

        bonus_amount = text_field("النقاط (+/-)", value="0", width=160,
                                  keyboard_type=ft.KeyboardType.NUMBER)
        bonus_reason = text_field("السبب", width=280)
        bonus_result = ft.Text("", color=SUCCESS, size=FS_SMALL)

        def add_bonus(e):
            bonus_result.value = ""
            try:
                amt = int(bonus_amount.value or 0)
                if amt == 0:
                    raise ValueError("أدخل عدداً غير صفري.")
                add_loyalty_points(cust["id"], amt,
                                   bonus_reason.value or "مكافأة يدوية",
                                   performed_by=self.user.get(
                                       "cashier_code", ""))
                fresh = get_customer_by_id(cust["id"])
                points_display.value = str(fresh["loyalty_points"])
                bonus_result.value = f"تم {amt:+d} نقطة."
                bonus_result.color = SUCCESS
                bonus_amount.value = "0"
                bonus_reason.value = ""
                for cc in (points_display, bonus_result, bonus_amount,
                           bonus_reason):
                    try:
                        cc.update()
                    except Exception:
                        pass
                new_log = get_loyalty_log(cust["id"], limit=200)
                history_holder.content = render_history(new_log)
                try:
                    history_holder.update()
                except Exception:
                    pass
            except Exception as ex:
                bonus_result.value = str(ex); bonus_result.color = DANGER
                try:
                    bonus_result.update()
                except Exception:
                    pass

        def close(e=None): self.page.close(dlg)

        header_info = ft.Column([
            ft.Text(f"{cust['name']} ({cust['code']})",
                    color=TEXT_PRIMARY, size=FS_SECTION,
                    weight=ft.FontWeight.W_800),
            ft.Text(f"{cust['phone'] or '—'} • "
                    f"{cust['address'] or '—'} • "
                    f"{cust['governorate'] or '—'}",
                    color=TEXT_MUTED, size=FS_SMALL),
        ], spacing=2)

        content = ft.Column([
            ft.Row([header_info, ft.Container(expand=True),
                    ft.Column([ft.Text("النقاط الحالية",
                                       color=TEXT_MUTED, size=FS_TINY),
                               points_display],
                              spacing=0,
                              horizontal_alignment=ft.CrossAxisAlignment.END)]),
            ft.Container(height=SP_SM), divider(),
            ft.Container(height=SP_SM),
            ft.Text("إضافة نقاط يدوية",
                    color=TEXT_PRIMARY, size=FS_SMALL,
                    weight=ft.FontWeight.W_700),
            ft.Row([bonus_amount, bonus_reason,
                    primary_button("إضافة", add_bonus,
                                   icon=ft.icons.ADD, width=110)],
                   spacing=SP_SM),
            bonus_result,
            ft.Container(height=SP_SM), divider(),
            ft.Container(height=SP_SM),
            ft.Text("سجل الحركات", color=TEXT_PRIMARY, size=FS_SMALL,
                    weight=ft.FontWeight.W_700),
            ft.Container(height=SP_SM),
            ft.Container(content=history_holder, height=340, expand=True),
        ], spacing=SP_SM, scroll=ft.ScrollMode.AUTO, width=760, height=640)

        dlg = ft.AlertDialog(
            modal=True, bgcolor=BG_CARD,
            title=ft.Text(f"نقاط العميل — {cust['name']}",
                          color=TEXT_PRIMARY, weight=ft.FontWeight.W_700,
                          size=FS_SECTION),
            content=content,
            actions=[ghost_button("إغلاق", close, width=110)])
        self.page.open(dlg)


# --------------------------- POS ---------------------------
class POSView:
    def __init__(self, app, page, user):
        self.app = app; self.page = page; self.user = user
        self.currency = get_currency_symbol()
        self.cart = []
        self.selected_customer = None
        self.discount_enabled = False
        self.loyalty_enabled = False
        self.commission_enabled = True  # DEFAULT ON per §1.3
        self._pending_loyalty_used = 0

        self.invoice_no_text = ft.Text("", color=TEXT_PRIMARY,
                                       size=FS_SECTION,
                                       weight=ft.FontWeight.W_800)
        self.datetime_text = ft.Text("", color=TEXT_MUTED, size=FS_SMALL)
        self.loyalty_top_text = ft.Text("—", color=WARNING, size=FS_BODY,
                                        weight=ft.FontWeight.W_800)
        self.cashier_code_text = ft.Text(
            self.user.get("cashier_code") or "—",
            color=TEXT_PRIMARY, size=FS_SECTION,
            weight=ft.FontWeight.W_700)

        self.customer_dd = self._build_customer_dropdown()
        self.cust_search = text_field(
            "بحث عميل (اسم/كود/هاتف)…",
            prefix_icon=ft.icons.SEARCH,
            on_change=self._on_customer_search,
            width=200)
        self.cust_search_results = ft.Column(
            spacing=0, height=100, scroll=ft.ScrollMode.AUTO)
        self.cust_search_wrap = ft.Container(
            content=self.cust_search_results, bgcolor=BG_INPUT,
            border=ft.border.all(1, BORDER), border_radius=RADIUS_SM,
            padding=SP_XS, visible=False)

        self.cust_phone = ft.Text("—", color=TEXT_SECONDARY, size=FS_SMALL)
        self.cust_code = ft.Text("—", color=SUCCESS, size=FS_SMALL)
        self.cust_points = ft.Text("0", color=WARNING, size=FS_BODY,
                                   weight=ft.FontWeight.W_800)

        self.search_input = text_field(
            "ابحث بالكود/الاسم…", prefix_icon=ft.icons.SEARCH,
            on_change=self._on_search, on_submit=self._on_search_submit,
            autofocus=True)
        self.search_results = ft.Column(spacing=0, height=120,
                                        scroll=ft.ScrollMode.AUTO)
        self.search_wrapper = ft.Container(
            content=self.search_results, bgcolor=BG_INPUT,
            border=ft.border.all(1, BORDER), border_radius=RADIUS_SM,
            padding=SP_XS, visible=False)

        self.cart_table = ft.DataTable(
            bgcolor=BG_INPUT,
            vertical_lines=ft.border.BorderSide(1, BORDER),
            horizontal_lines=ft.border.BorderSide(1, BORDER),
            heading_row_color=BG_CARD_HOVER, heading_row_height=42,
            data_row_min_height=44, data_row_max_height=64,
            column_spacing=6, divider_thickness=0,
            columns=[
                ft.DataColumn(label=ft.Text("الصنف", color=TEXT_PRIMARY,
                                            size=FS_SMALL,
                                            weight=ft.FontWeight.W_700)),
                ft.DataColumn(label=ft.Text("الكمية", color=TEXT_PRIMARY,
                                            size=FS_SMALL,
                                            weight=ft.FontWeight.W_700),
                              numeric=True),
                ft.DataColumn(label=ft.Text("سعر القطعة",
                                            color=TEXT_PRIMARY,
                                            size=FS_SMALL,
                                            weight=ft.FontWeight.W_700),
                              numeric=True),
                ft.DataColumn(label=ft.Text("الإجمالي",
                                            color=TEXT_PRIMARY,
                                            size=FS_SMALL,
                                            weight=ft.FontWeight.W_700),
                              numeric=True),
                ft.DataColumn(label=ft.Text("", color=TEXT_MUTED,
                                            size=FS_TINY)),
            ],
            rows=[])
        self.cart_wrapper = ft.Column([self.cart_table],
                                      scroll=ft.ScrollMode.AUTO, expand=True)
        self.cart_empty = empty_state("السلة فارغة.",
                                      icon=ft.icons.SHOPPING_CART_OUTLINED)

        self.items_count_text = ft.Text("0", color=TEXT_PRIMARY, size=18,
                                        weight=ft.FontWeight.W_800)
        self.subtotal_text = ft.Text(money_str(0, self.currency),
                                     color=TEXT_PRIMARY, size=FS_SECTION,
                                     weight=ft.FontWeight.W_700)
        self.discount_text = ft.Text(f"- {money_str(0, self.currency)}",
                                     color=WARNING, size=FS_BODY)
        self.loyalty_discount_text = ft.Text(
            f"- {money_str(0, self.currency)}", color=INFO, size=FS_BODY)
        self.commission_text = ft.Text(f"+ {money_str(0, self.currency)}",
                                       color=INFO, size=FS_BODY)
        self.net_total_text = ft.Text(money_str(0, self.currency),
                                      color=TEXT_PRIMARY, size=26,
                                      weight=ft.FontWeight.W_900)

        self.discount_check = ft.Checkbox(
            label="تفعيل الخصم", value=False,
            on_change=self._on_discount_toggle, fill_color=ACCENT,
            check_color=BG_BLACK,
            label_style=ft.TextStyle(color=TEXT_SECONDARY, size=FS_BODY))
        self.discount_type_dd = dropdown(
            "النوع", ["ثابت", "نسبة مئوية"], value="ثابت", width=140,
            on_change=lambda e: self._recalc())
        self.discount_input = text_field(
            "القيمة", value="0", width=120,
            on_change=lambda e: self._recalc(),
            keyboard_type=ft.KeyboardType.NUMBER)
        self.discount_container = ft.Row(
            [self.discount_type_dd, self.discount_input],
            spacing=SP_SM, visible=False)

        self.loyalty_check = ft.Checkbox(
            label="استخدام نقاط الولاء", value=False,
            on_change=self._on_loyalty_toggle, fill_color=ACCENT,
            check_color=BG_BLACK,
            label_style=ft.TextStyle(color=TEXT_SECONDARY, size=FS_BODY))
        self.loyalty_points_field = text_field(
            "النقاط المستخدمة", value="0", width=200,
            on_change=lambda e: self._recalc(),
            keyboard_type=ft.KeyboardType.NUMBER)
        self.loyalty_available_text = ft.Text("", color=SUCCESS,
                                              size=FS_TINY)
        self.loyalty_container = ft.Column(
            [self.loyalty_points_field, self.loyalty_available_text],
            spacing=4, visible=False)

        self.commission_check = ft.Checkbox(
            label="عمولة التحويل (1%)", value=True,  # DEFAULT ON
            on_change=self._on_commission_toggle, fill_color=ACCENT,
            check_color=BG_BLACK,
            label_style=ft.TextStyle(color=TEXT_SECONDARY, size=FS_BODY))
        self.commission_hint = ft.Text("مفعلة افتراضياً — تُحسب 1% "
                                       "من الإجمالي (تقريب لأقرب 5 ج.م)",
                                       color=TEXT_MUTED, size=FS_TINY,
                                       visible=True)

        self.save_btn = primary_button("حفظ", self._on_save_click,
                                       icon=ft.icons.SAVE, width=135,
                                       height=48)
        self.print_btn = primary_button("طباعة", self._on_print_click,
                                        icon=ft.icons.PRINT, width=135,
                                        height=48)
        self._update_header()
        self._recalc()
        try:
            self.page.run_task(self._clock_loop)
        except Exception:
            pass

    def _build_customer_dropdown(self):
        customers = get_all_customers()
        opts = [(str(c["id"]),
                 f"{c['name']} ({c['code']}) — {c['phone'] or '—'}")
                for c in customers]
        return keyed_dropdown("العميل *", opts, width=340,
                              on_change=self._on_customer_selected)

    def _on_customer_search(self, e):
        term = (self.cust_search.value or "").strip()
        self.cust_search_results.controls.clear()
        if not term:
            self.cust_search_wrap.visible = False
            try:
                self.cust_search_wrap.update()
            except Exception:
                pass
            return
        results = flexible_customer_search(term)
        if len(results) == 0:
            self.cust_search_results.controls.append(
                ft.Container(content=ft.Text("لا نتائج.", color=TEXT_MUTED,
                                             size=FS_BODY), padding=8))
        else:
            for c in results[:30]:
                self.cust_search_results.controls.append(
                    self._customer_result_row(c))
        self.cust_search_wrap.visible = True
        try:
            self.cust_search_wrap.update()
            self.cust_search_results.update()
        except Exception:
            pass

    def _customer_result_row(self, c):
        def click(e):
            try:
                self.customer_dd.value = str(c["id"])
                self.customer_dd.update()
                self._on_customer_selected(None)
            except Exception:
                pass
            self.cust_search.value = ""
            self.cust_search_wrap.visible = False
            try:
                self.cust_search.update()
                self.cust_search_wrap.update()
            except Exception:
                pass

        return ft.Container(
            content=ft.Row([
                ft.Column([
                    ft.Text(c["name"], color=TEXT_PRIMARY, size=FS_SMALL,
                            weight=ft.FontWeight.W_600),
                    ft.Text(f"{c['code']}  ·  {c['phone'] or '—'}",
                            color=TEXT_MUTED, size=FS_TINY)],
                    spacing=0, tight=True, expand=True),
            ]),
            padding=ft.padding.symmetric(horizontal=10, vertical=6),
            border_radius=RADIUS_SM, on_click=click, ink=True,
            on_hover=_hv_ghost)

    def _on_customer_selected(self, e):
        cid = self.customer_dd.value
        if not cid:
            self.selected_customer = get_quick_customer()
        else:
            self.selected_customer = get_customer_by_id(int(cid))
        self._refresh_customer_info()
        self._recalc()

    def _refresh_customer_info(self):
        c = self.selected_customer
        if not c:
            c = get_quick_customer()
            self.selected_customer = c
        is_quick = (c and c.get("code") == QUICK_CUSTOMER_CODE)
        if not c:
            self.cust_phone.value = "—"
            self.cust_code.value = "—"
            self.cust_points.value = "0"
            self.loyalty_top_text.value = "—"
            self.loyalty_available_text.value = ""
        else:
            self.cust_phone.value = c["phone"] or "—"
            self.cust_code.value = c["code"]
            if is_quick:
                self.cust_points.value = "—"
                self.loyalty_top_text.value = "—"
                self.loyalty_available_text.value = (
                    "عميل سريع — لا يحتسب نقاط ولاء")
            else:
                self.cust_points.value = str(c["loyalty_points"])
                self.loyalty_top_text.value = f"{c['loyalty_points']}"
                self.loyalty_available_text.value = (
                    f"المتاح: {c['loyalty_points']} نقطة")
        try:
            self.loyalty_check.disabled = is_quick
            self.loyalty_check.update()
        except Exception:
            pass
        if is_quick:
            self.loyalty_check.value = False
            self.loyalty_enabled = False
            self.loyalty_container.visible = False
            try:
                self.loyalty_container.update()
            except Exception:
                pass
        for t in (self.cust_phone, self.cust_code, self.cust_points,
                  self.loyalty_top_text, self.loyalty_available_text):
            try:
                t.update()
            except Exception:
                pass

    def build(self):
        left = ft.Column([
            self._invoice_bar(), ft.Container(height=SP_SM),
            self._customer_row(), ft.Container(height=SP_SM),
            self._search_block(), ft.Container(height=SP_SM),
            self._cart_block(),
        ], spacing=0, expand=True)
        right = ft.Container(
            content=ft.Column([self._totals_card()], spacing=SP_SM),
            width=360)
        return ft.Row([ft.Container(content=left, expand=True),
                       ft.Container(width=SP_MD), right],
                      vertical_alignment=ft.CrossAxisAlignment.START,
                      expand=True)

    def _invoice_bar(self):
        return card(ft.Row([
            ft.Column([ft.Text("فاتورة", color=TEXT_MUTED, size=FS_TINY),
                       self.invoice_no_text], spacing=0, tight=True),
            ft.Container(width=SP_LG),
            ft.Column([ft.Text("كود الكاشير", color=TEXT_MUTED,
                               size=FS_TINY),
                       self.cashier_code_text], spacing=0, tight=True),
            ft.Container(width=SP_LG),
            ft.Column([ft.Text("نقاط الولاء", color=TEXT_MUTED,
                               size=FS_TINY),
                       self.loyalty_top_text], spacing=0, tight=True),
            ft.Container(expand=True),
            ft.Column([ft.Text("الوقت", color=TEXT_MUTED, size=FS_TINY),
                       self.datetime_text], spacing=0, tight=True,
                      horizontal_alignment=ft.CrossAxisAlignment.END),
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=SP_SM, hover=False)

    def _customer_row(self):
        return card(ft.Column([
            ft.Row([
                self.customer_dd,
                ft.Container(width=SP_SM),
                self.cust_search,
            ], spacing=SP_SM, wrap=True),
            self.cust_search_wrap,
            ft.Row([
                ft.Text("الهاتف:", color=TEXT_MUTED, size=FS_TINY),
                self.cust_phone, ft.Container(width=SP_MD),
                ft.Text("الكود:", color=TEXT_MUTED, size=FS_TINY),
                self.cust_code, ft.Container(width=SP_MD),
                ft.Icon(ft.icons.STAR, size=14, color=WARNING),
                self.cust_points,
                ft.Text("نقطة", color=TEXT_MUTED, size=FS_TINY),
            ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ], spacing=SP_SM), padding=SP_SM, hover=False)

    def _search_block(self):
        return card(ft.Column([self.search_input, self.search_wrapper],
                              spacing=SP_SM), padding=SP_SM, hover=False)

    def _cart_block(self):
        return card(ft.Column([section_title("سلة المشتريات"),
                               ft.Container(height=SP_SM),
                               ft.Container(content=self.cart_wrapper,
                                            expand=True)],
                              spacing=0, expand=True),
                    padding=SP_MD, hover=False, expand=True)

    def _totals_card(self):
        return card(ft.Column([
            ft.Row([ft.Text("عدد القطع", color=TEXT_SECONDARY, size=FS_BODY),
                    ft.Container(expand=True), self.items_count_text]),
            divider(),
            ft.Row([ft.Text("المجموع الفرعي", color=TEXT_SECONDARY,
                            size=FS_BODY),
                    ft.Container(expand=True), self.subtotal_text]),
            ft.Row([ft.Text("خصم يدوي", color=TEXT_SECONDARY,
                            size=FS_BODY),
                    ft.Container(expand=True), self.discount_text]),
            ft.Row([ft.Text("خصم النقاط", color=TEXT_SECONDARY,
                            size=FS_BODY),
                    ft.Container(expand=True), self.loyalty_discount_text]),
            ft.Row([ft.Text("عمولة التحويل", color=TEXT_SECONDARY,
                            size=FS_BODY),
                    ft.Container(expand=True), self.commission_text]),
            ft.Container(height=SP_SM),
            self.discount_check, self.discount_container, divider(),
            self.loyalty_check, self.loyalty_container, divider(),
            self.commission_check, self.commission_hint, divider(),
            ft.Text("الإجمالي النهائي", color=TEXT_MUTED, size=FS_TINY,
                    weight=ft.FontWeight.W_700),
            self.net_total_text, ft.Container(height=SP_SM),
            ft.Row([self.save_btn, self.print_btn],
                   alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                   spacing=SP_SM),
            ft.Container(height=SP_SM),
            ghost_button("تفريغ السلة", self._on_clear_cart,
                         icon=ft.icons.DELETE_OUTLINE, width=280,
                         danger=True),
        ], spacing=SP_SM), padding=SP_MD, hover=False)

    async def _clock_loop(self):
        import asyncio
        while True:
            await asyncio.sleep(1)
            try:
                self._update_header()
            except Exception:
                return

    def _update_header(self):
        try:
            self.invoice_no_text.value = f"#{get_next_invoice_number()}"
            self.datetime_text.value = datetime.now().strftime(
                "%d/%m/%Y %H:%M:%S")
            self.invoice_no_text.update()
            self.datetime_text.update()
        except Exception:
            pass

    def _on_search(self, e):
        term = (self.search_input.value or "").strip()
        self.search_results.controls.clear()
        if not term:
            self.search_wrapper.visible = False
            try:
                self.search_wrapper.update()
            except Exception:
                pass
            return
        results = search_products(term, limit=30)
        if not results:
            self.search_results.controls.append(
                ft.Container(content=ft.Text("لا نتائج.", color=TEXT_MUTED,
                                             size=FS_BODY), padding=10))
        else:
            for p in results:
                self.search_results.controls.append(self._result_row(p))
        self.search_wrapper.visible = True
        try:
            self.search_wrapper.update()
            self.search_results.update()
        except Exception:
            pass

    def _on_search_submit(self, e):
        term = (self.search_input.value or "").strip()
        if not term:
            return
        p = get_product_by_code(term)
        if p is None:
            r = search_products(term, limit=1)
            p = r[0] if r else None
        if p:
            self._add_to_cart(p["id"])
            self._clear_search()

    def _clear_search(self):
        self.search_input.value = ""
        self.search_wrapper.visible = False
        self.search_input.focus()
        try:
            self.search_input.update()
            self.search_wrapper.update()
        except Exception:
            pass

    def _result_row(self, p):
        stock_color = SUCCESS if p["stock_qty"] > 0 else DANGER

        def click(e):
            self._add_to_cart(p["id"]); self._clear_search()

        return ft.Container(
            content=ft.Row([
                ft.Column([ft.Text(p["name"], color=TEXT_PRIMARY,
                                   size=FS_BODY,
                                   weight=ft.FontWeight.W_600),
                           ft.Text(p["code"], color=TEXT_MUTED,
                                   size=FS_TINY)],
                          spacing=0, tight=True, expand=True),
                ft.Text(money_str(p["wholesale_price"], self.currency),
                        color=TEXT_PRIMARY, size=FS_BODY,
                        weight=ft.FontWeight.W_700),
                ft.Container(width=SP_SM),
                chip(f"{p['stock_qty']}", color=stock_color, bg=BG_CARD),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.symmetric(horizontal=12, vertical=6),
            border_radius=RADIUS_SM, on_click=click, ink=True,
            on_hover=_hv_ghost)

    def _add_to_cart(self, pid):
        p = get_product_by_id(pid)
        if p is None:
            return
        if p["stock_qty"] <= 0:
            snack(self.page, f"'{p['name']}' غير متوفر.", kind="error")
            return
        for l in self.cart:
            if l["product_code"] == p["code"]:
                if l["quantity"] + 1 > p["stock_qty"]:
                    snack(self.page, "المخزون غير كافٍ.", kind="warning")
                    return
                l["quantity"] += 1
                self._refresh_cart(); return
        self.cart.append({
            "product_code": p["code"], "product_name": p["name"],
            "quantity": 1, "price": float(p["wholesale_price"]),
            "stock": int(p["stock_qty"])})
        self._refresh_cart()

    def _inc(self, i):
        l = self.cart[i]
        if l["quantity"] + 1 > l["stock"]:
            snack(self.page, f"المتاح {l['stock']}.", kind="warning")
            return
        l["quantity"] += 1; self._refresh_cart()

    def _dec(self, i):
        self.cart[i]["quantity"] -= 1
        if self.cart[i]["quantity"] <= 0:
            self.cart.pop(i)
        self._refresh_cart()

    def _remove(self, i):
        self.cart.pop(i); self._refresh_cart()

    def _edit_price(self, i):
        l = self.cart[i]
        pf = text_field("السعر", value=f"{l['price']:.2f}", width=240,
                        keyboard_type=ft.KeyboardType.NUMBER)
        err = ft.Text("", color=DANGER, size=FS_SMALL, visible=False)

        def save(e):
            err.visible = False
            try:
                v = float(pf.value or 0)
                if v <= 0:
                    raise ValueError("> 0.")
                self.cart[i]["price"] = round(v, 2)
            except Exception as ex:
                err.value = str(ex); err.visible = True; err.update(); return
            self.page.close(dlg); self._refresh_cart()

        def cancel(e=None): self.page.close(dlg)

        dlg = ft.AlertDialog(
            modal=True, bgcolor=BG_CARD,
            title=ft.Text(f"تعديل سعر: {l['product_name']}",
                          color=TEXT_PRIMARY, weight=ft.FontWeight.W_700,
                          size=FS_SECTION),
            content=ft.Column([pf, err], spacing=SP_SM, width=260),
            actions=[ghost_button("إلغاء", cancel, width=110),
                     primary_button("حفظ", save, icon=ft.icons.CHECK,
                                    width=110)])
        self.page.open(dlg)

    def _refresh_cart(self):
        if not self.cart:
            self.cart_wrapper.controls = [self.cart_empty]
        else:
            rows = []
            for i, l in enumerate(self.cart):
                sub = l["price"] * l["quantity"]
                del_btn = ft.IconButton(
                    icon=ft.icons.DELETE, icon_size=18,
                    icon_color=DANGER, tooltip="حذف الصنف",
                    on_click=lambda e, i=i: self._remove(i))
                rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Column([
                        ft.Text(l["product_name"], color=TEXT_PRIMARY,
                                size=FS_SMALL, weight=ft.FontWeight.W_600,
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS),
                        ft.Text(l["product_code"], color=TEXT_MUTED,
                                size=FS_TINY)],
                        spacing=0, tight=True)),
                    ft.DataCell(ft.Row([
                        ft.IconButton(icon=ft.icons.REMOVE, icon_size=16,
                                      icon_color=TEXT_PRIMARY,
                                      on_click=lambda e, i=i: self._dec(i)),
                        ft.Text(str(l["quantity"]), color=TEXT_PRIMARY,
                                size=FS_BODY, weight=ft.FontWeight.W_700),
                        ft.IconButton(icon=ft.icons.ADD, icon_size=16,
                                      icon_color=TEXT_PRIMARY,
                                      on_click=lambda e, i=i: self._inc(i)),
                    ], spacing=0, tight=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER)),
                    ft.DataCell(ft.Container(
                        content=ft.Text(money_str(l["price"], self.currency),
                                        color=TEXT_SECONDARY, size=FS_SMALL),
                        on_click=lambda e, i=i: self._edit_price(i),
                        tooltip="تعديل السعر")),
                    ft.DataCell(ft.Text(money_str(sub, self.currency),
                                        color=TEXT_PRIMARY, size=FS_SMALL,
                                        weight=ft.FontWeight.W_700)),
                    ft.DataCell(del_btn),
                ]))
            self.cart_table.rows = rows
            self.cart_wrapper.controls = [self.cart_table]
        self._recalc()
        try:
            self.cart_wrapper.update()
        except Exception:
            pass

    def _on_discount_toggle(self, e):
        self.discount_enabled = bool(self.discount_check.value)
        self.discount_container.visible = self.discount_enabled
        if not self.discount_enabled:
            self.discount_input.value = "0"
        try:
            self.discount_container.update()
        except Exception:
            pass
        self._recalc()

    def _on_loyalty_toggle(self, e):
        self.loyalty_enabled = bool(self.loyalty_check.value)
        self.loyalty_container.visible = self.loyalty_enabled
        if not self.loyalty_enabled:
            self.loyalty_points_field.value = "0"
        try:
            self.loyalty_container.update()
        except Exception:
            pass
        self._recalc()

    def _on_commission_toggle(self, e):
        self.commission_enabled = bool(self.commission_check.value)
        try:
            self.commission_hint.update()
        except Exception:
            pass
        self._recalc()

    def _commission_amount(self):
        if not self.commission_enabled:
            return 0.0
        subtotal = sum(l["price"] * l["quantity"] for l in self.cart)
        base = max(0.0, subtotal - self._manual_disc() - self._loyalty_disc())
        return float(round_to_5(base * 0.01))

    def _recalc(self):
        self.currency = get_currency_symbol()
        total_items = sum(l["quantity"] for l in self.cart)
        subtotal = sum(l["price"] * l["quantity"] for l in self.cart)
        if self.discount_enabled:
            try:
                dv = float(self.discount_input.value or 0)
            except ValueError:
                dv = 0.0
            if self.discount_type_dd.value == "نسبة مئوية":
                manual = subtotal * (dv / 100.0)
            else:
                manual = dv
            manual = max(0.0, min(manual, subtotal))
        else:
            manual = 0.0
        loyalty_disc = 0.0
        loyalty_used = 0
        is_quick = (self.selected_customer is None or
                    self.selected_customer.get("code") == QUICK_CUSTOMER_CODE)
        if self.loyalty_enabled and self.selected_customer and not is_quick:
            try:
                avail = int(self.selected_customer.get("loyalty_points", 0))
                req = int(self.loyalty_points_field.value or 0)
                req = max(0, min(req, avail))
                max_money_pts = int((subtotal - manual) * POINTS_PER_EGP)
                req = min(req, max_money_pts)
                loyalty_used = req
                loyalty_disc = req / POINTS_PER_EGP
            except (ValueError, TypeError):
                loyalty_used = 0
        self._pending_loyalty_used = loyalty_used
        commission = self._commission_amount()
        net = max(0.0, subtotal - manual - loyalty_disc + commission)
        try:
            self.items_count_text.value = str(total_items)
            self.subtotal_text.value = money_str(subtotal, self.currency)
            self.discount_text.value = f"- {money_str(manual, self.currency)}"
            self.loyalty_discount_text.value = (
                f"- {money_str(loyalty_disc, self.currency)}")
            self.commission_text.value = (
                f"+ {money_str(commission, self.currency)}")
            self.net_total_text.value = money_str(net, self.currency)
            for t in (self.items_count_text, self.subtotal_text,
                      self.discount_text, self.loyalty_discount_text,
                      self.commission_text, self.net_total_text):
                t.update()
        except Exception:
            pass

    def _manual_disc(self):
        if not self.discount_enabled:
            return 0.0
        subtotal = sum(l["price"] * l["quantity"] for l in self.cart)
        try:
            dv = float(self.discount_input.value or 0)
        except ValueError:
            dv = 0.0
        if self.discount_type_dd.value == "نسبة مئوية":
            return min(subtotal, subtotal * dv / 100.0)
        return min(subtotal, dv)

    def _loyalty_disc(self):
        return getattr(self, "_pending_loyalty_used", 0) / POINTS_PER_EGP

    def _on_save_click(self, e):
        self._confirm_and_save(open_preview=False)

    def _on_print_click(self, e):
        self._confirm_and_save(open_preview=True)

    def _confirm_and_save(self, open_preview=False):
        if not self.cart:
            snack(self.page, "السلة فارغة.", kind="warning"); return
        self._recalc()
        commission = self._commission_amount()
        net = max(0.0, sum(l["price"] * l["quantity"] for l in self.cart)
                  - self._manual_disc() - self._loyalty_disc() + commission)
        cust = (self.selected_customer
                or get_quick_customer()
                or {"name": QUICK_CUSTOMER_NAME})
        action = "حفظ وطباعة" if open_preview else "حفظ"
        msg = (f"{action} الفاتورة؟\n"
               f"العميل: {cust['name']}\n"
               f"القطع: {sum(l['quantity'] for l in self.cart)}\n"
               f"الإجمالي: {money_str(net, self.currency)}")
        confirm_dialog(self.page, "تأكيد", msg,
                       lambda: self._perform_save(open_preview),
                       confirm_text="تأكيد",
                       cancel_text="إلغاء", danger=False)

    def _perform_save(self, open_preview=False):
        c = self.selected_customer or get_quick_customer()
        if c:
            c = get_customer_by_id(c["id"]) or c
            cid, ccode = c["id"], c["code"]; cname = c["name"]
            cphone = c["phone"] or ""; caddr = c["address"] or ""
            cgov = c["governorate"] or ""
        else:
            cid, ccode, cname, cphone, caddr, cgov = (
                None, "", QUICK_CUSTOMER_NAME, "0000", "0000", "")
        manual = self._manual_disc()
        loyalty_used = getattr(self, "_pending_loyalty_used", 0)
        loyalty_disc = loyalty_used / POINTS_PER_EGP
        total_disc = manual + loyalty_disc
        commission = self._commission_amount()
        items_payload = [
            {"product_code": l["product_code"],
             "quantity": l["quantity"], "price": l["price"]}
            for l in self.cart
        ]
        if commission > 0:
            items_payload.append({
                "product_code": COMMISSION_CODE,
                "product_name": "عمولة التحويل",
                "quantity": 1, "price": commission, "is_fee": True,
            })
        try:
            inv = create_invoice(
                customer_id=cid, customer_code=ccode, customer_name=cname,
                customer_phone=cphone, customer_address=caddr,
                customer_governorate=cgov,
                items=items_payload,
                discount=total_disc,
                cashier_name=self.user["username"],
                cashier_code=self.user.get("cashier_code", ""),
                loyalty_points_used=loyalty_used)
        except Exception as ex:
            snack(self.page, str(ex), kind="error"); return

        self.cart.clear()
        self.selected_customer = None
        try:
            self.customer_dd.value = None
        except Exception:
            pass
        self.discount_check.value = False
        self.discount_enabled = False
        self.discount_container.visible = False
        self.discount_input.value = "0"
        self.loyalty_check.value = False
        self.loyalty_enabled = False
        self.loyalty_container.visible = False
        self.loyalty_points_field.value = "0"
        self.commission_check.value = True
        self.commission_enabled = True
        self.commission_hint.visible = True
        self._pending_loyalty_used = 0
        self._refresh_cart()
        self._refresh_customer_info()
        self._update_header()
        for ctrl in (self.customer_dd, self.discount_check,
                     self.discount_container, self.loyalty_check,
                     self.loyalty_container, self.commission_check,
                     self.commission_hint):
            try:
                ctrl.update()
            except Exception:
                pass
        snack(self.page,
              f"تم حفظ #{inv['invoice_number']} (قيد الدفع).",
              kind="success")
        if inv.get("_welcome_bonus_granted"):
            snack(self.page,
                  f"🎁 تم منح {WELCOME_BONUS_POINTS} نقطة ترحيبية للعميل الجديد.",
                  kind="success")

        inv = enrich_invoice_for_print(inv)

        try:
            path = invoice_pdf_path(inv["invoice_number"], "thermal")
            generate_pdf_receipt(inv, path)
        except Exception:
            path = None

        if open_preview:
            open_thermal_preview(self.page, inv)
        elif path:
            snack(self.page, f"الإيصال محفوظ: {os.path.basename(path)}",
                  kind="info")

    def _on_clear_cart(self, e):
        if not self.cart:
            return
        self.cart.clear()
        self._pending_loyalty_used = 0
        self._refresh_cart()


# --------------------------- RETURNS ---------------------------
class ReturnsView:
    """
    Returns screen — list-first workflow.

    • Main view: table of ALL returns (R0001, R0002, …) with inline
      actions: Edit / Delete / Print (thermal return slip).
    • "إضافة مرتجع" button → popup dialog: invoice search → header + items
      (only from that invoice) → per-item Qty + Reason (عيب مصنعي /
      مرتجع عادي) → submit.
    • On submit → new R-code generated → stock restored per item reason
      (normal → stock_qty; defect → defect_qty) → cash flow adjusted
      automatically (via returns.total_refund) → list refreshed.
    """
    def __init__(self, app, page, user):
        self.app = app; self.page = page; self.user = user
        self.currency = get_currency_symbol()

        self.search = text_field(
            "بحث (كود المرتجع / رقم الفاتورة / العميل)…",
            prefix_icon=ft.icons.SEARCH,
            on_change=lambda e: self._refresh(),
            width=340)
        self.table = ft.Container(expand=True)

        self.dlg = None
        self.current_invoice = None
        self.item_rows = []
        self.invoice_input = None
        self.search_hint = None
        self.details_area = None
        self.notes_input = None

    # ---------- build ----------
    def build(self):
        header = ft.Row([
            page_title("المرتجعات", "قائمة المرتجعات + إضافة مرتجع"),
            ft.Container(expand=True),
            self.search,
            primary_button("إضافة مرتجع", self._add_dialog,
                           icon=ft.icons.ADD, width=170),
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=SP_MD)
        self._refresh()
        return ft.Column([
            header, ft.Container(height=SP_SM),
            card(ft.Column([self.table], expand=True, spacing=0),
                 padding=0, hover=False, expand=True),
        ], spacing=0, expand=True)

    def _refresh(self):
        returns = get_returns()
        term = (self.search.value or "").strip().lower()
        if term:
            returns = [r for r in returns
                       if term in (r.get("return_code") or "").lower()
                       or term in str(r.get("invoice_number") or "")
                       or term in (r.get("customer_name") or "").lower()]
        if not returns:
            self.table.content = empty_state("لا مرتجعات.", icon=ft.icons.UNDO)
            try:
                self.table.update()
            except Exception:
                pass
            return
        rows = []
        for r in returns:
            label = RETURN_REASON_LABELS.get(
                r["reason_type"], r["reason_type"])
            color = (DANGER if r["reason_type"] == RETURN_REASON_DEFECT
                     else WARNING)
            rows.append([
                ft.Text(r.get("return_code") or "—", color=SUCCESS,
                        size=FS_SMALL, weight=ft.FontWeight.W_800,
                        max_lines=1),
                ft.Text(str(r.get("invoice_number") or "—"),
                        color=TEXT_PRIMARY, size=FS_SMALL, max_lines=1),
                ft.Text(r.get("customer_name") or "—", color=TEXT_PRIMARY,
                        size=FS_SMALL, max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS),
                chip(label, color=color),
                ft.Text(r["created_at"][:16], color=TEXT_SECONDARY,
                        size=FS_SMALL, max_lines=1),
                ft.Text(money_str(r["total_refund"], self.currency),
                        color=TEXT_PRIMARY, size=FS_SMALL,
                        weight=ft.FontWeight.W_700, max_lines=1),
            ])

        def row_actions(r):
            return [
                {"label": "تعديل", "icon": ft.icons.EDIT,
                 "handler": lambda r=r: self._edit_return(r)},
                {"label": "طباعة حرارية", "icon": ft.icons.PRINT,
                 "handler": lambda r=r: self._print_return(r)},
                {"label": "حذف", "icon": ft.icons.DELETE,
                 "handler": lambda r=r: self._delete_return(r),
                 "danger": True},
            ]

        self.table.content = data_table(
            self.page,
            [("الكود", 90), ("الفاتورة", 80), ("العميل", 140),
             ("النوع", 90), ("التاريخ", 120), ("القيمة", 100)],
            rows, "لا مرتجعات.", raw_data=returns,
            row_actions_builder=row_actions)
        try:
            self.table.update()
        except Exception:
            pass

    # ---------- Add Return popup ----------
    def _add_dialog(self, e=None):
        try:
            if self.dlg is not None:
                self.page.close(self.dlg)
        except Exception:
            pass
        self.current_invoice = None
        self.item_rows = []

        self.invoice_input = text_field(
            "رقم الفاتورة *", width=240,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_submit=lambda e: self._lookup())
        self.search_hint = ft.Text(
            "أدخل رقم الفاتورة ثم اضغط بحث",
            color=TEXT_MUTED, size=FS_SMALL)
        self.details_area = ft.Column([], spacing=SP_SM)
        self.notes_input = None

        body = ft.Column([
            self._search_card(),
            self.details_area,
        ], spacing=SP_SM, scroll=ft.ScrollMode.AUTO)

        def close(e=None):
            try:
                self.page.close(dlg)
            except Exception:
                pass
            self.dlg = None
            self._refresh()

        dlg = ft.AlertDialog(
            modal=True, bgcolor=BG_CARD,
            title=ft.Text("إضافة مرتجع", color=TEXT_PRIMARY,
                          weight=ft.FontWeight.W_700, size=FS_SECTION),
            content=ft.Container(content=body, width=820, height=620,
                                 padding=0),
            actions=[ghost_button("إغلاق", close, width=110)])
        self.dlg = dlg
        self.page.open(dlg)

    def _search_card(self):
        return card(ft.Row([
            self.invoice_input,
            primary_button("بحث", self._lookup,
                           icon=ft.icons.SEARCH, width=110),
            ft.Container(expand=True),
            self.search_hint,
        ], spacing=SP_SM,
            vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=SP_MD, hover=False)

    def _lookup(self, e=None):
        num = (self.invoice_input.value or "").strip()
        if not num:
            snack(self.page, "أدخل رقم الفاتورة.", kind="warning")
            return
        inv = get_invoice_by_number(num)
        if inv is None:
            self.search_hint.value = f"لا فاتورة برقم {num}."
            self.search_hint.color = DANGER
            try:
                self.search_hint.update()
            except Exception:
                pass
            return
        self.current_invoice = inv
        self.search_hint.value = (
            f"✓ تم العثور على الفاتورة #{inv['invoice_number']}")
        self.search_hint.color = SUCCESS
        try:
            self.search_hint.update()
        except Exception:
            pass
        self._render_invoice_content()

    def _render_invoice_content(self):
        inv = self.current_invoice
        if not inv:
            return

        # ---- Header ----
        header_card = card(ft.Column([
            ft.Row([
                ft.Column([
                    ft.Text(
                        f"فاتورة #{inv.get('invoice_number', inv['id'])}",
                        color=TEXT_PRIMARY, size=FS_SECTION,
                        weight=ft.FontWeight.W_800),
                    ft.Text(
                        f"العميل: {inv.get('customer_name') or '—'}",
                        color=TEXT_PRIMARY, size=FS_BODY),
                ], spacing=2, expand=True),
                ft.Column([
                    ft.Text(
                        f"التاريخ: {inv['created_at'][:16]}",
                        color=TEXT_SECONDARY, size=FS_SMALL),
                    ft.Text(
                        f"الإجمالي: "
                        f"{money_str(inv['net_total'], self.currency)}",
                        color=SUCCESS, size=FS_BODY,
                        weight=ft.FontWeight.W_700),
                ], spacing=2,
                    horizontal_alignment=ft.CrossAxisAlignment.END),
            ], vertical_alignment=ft.CrossAxisAlignment.START),
            ft.Row([
                ft.Text(
                    f"الهاتف: {inv.get('customer_phone') or '—'}",
                    color=TEXT_SECONDARY, size=FS_SMALL),
                ft.Text(
                    f"العنوان: {inv.get('customer_address') or '—'}",
                    color=TEXT_SECONDARY, size=FS_SMALL),
            ], spacing=SP_LG),
        ], spacing=SP_SM), padding=SP_MD, hover=False)

        # ---- Eligible items ----
        eligible = get_return_items_for_invoice(inv["id"])
        self.item_rows = []
        if not eligible:
            items_card = card(
                ft.Text(
                    "لا توجد أصناف متاحة للإرجاع من هذه الفاتورة.",
                    color=TEXT_MUTED, size=FS_BODY),
                padding=SP_MD, hover=False)
        else:
            rows_controls = []
            for it in eligible:
                qty_field = text_field(
                    "", value="0", width=90,
                    keyboard_type=ft.KeyboardType.NUMBER)
                reason_dd = dropdown(
                    "السبب", ["مرتجع عادي", "عيب مصنعي"],
                    value="مرتجع عادي", width=170)
                self.item_rows.append({
                    "product_code": it["product_code"],
                    "product_name": it["product_name"],
                    "remaining": it["remaining"],
                    "price": it["price"],
                    "qty_field": qty_field,
                    "reason_dd": reason_dd,
                })
                rows_controls.append(ft.Container(
                    content=ft.Row([
                        ft.Column([
                            ft.Text(it["product_name"],
                                    color=TEXT_PRIMARY, size=FS_SMALL,
                                    weight=ft.FontWeight.W_600,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Text(
                                f"{it['product_code']}  •  "
                                f"متبقي {it['remaining']}  •  "
                                f"{money_str(it['price'], self.currency)}",
                                color=TEXT_MUTED, size=FS_TINY),
                        ], spacing=0, tight=True, expand=True),
                        qty_field,
                        reason_dd,
                    ], spacing=SP_SM,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=SP_SM, bgcolor=BG_INPUT,
                    border_radius=RADIUS_SM))
            items_card = card(ft.Column([
                section_title(
                    "أصناف الفاتورة — أدخل الكمية والسبب لكل صنف"),
                ft.Text("اترك الكمية 0 لتصنيف غير مرتجع.",
                        color=TEXT_MUTED, size=FS_TINY),
                ft.Container(height=SP_SM),
                ft.Column(rows_controls, spacing=SP_SM),
            ], spacing=SP_SM), padding=SP_MD, hover=False)

        # ---- Notes ----
        self.notes_input = text_field(
            "ملاحظات (اختياري)", width=500, multiline=True)

        submit_btn = primary_button(
            "تنفيذ المرتجع", self._commit_return,
            icon=ft.icons.UNDO, width=200)

        self.details_area.controls = [
            header_card,
            items_card,
            self.notes_input,
            ft.Row([ft.Container(expand=True), submit_btn]),
        ]
        try:
            self.details_area.update()
        except Exception:
            pass

    def _commit_return(self, e=None):
        if not self.current_invoice:
            return

        items = []
        for row in self.item_rows:
            try:
                qty = int(row["qty_field"].value or 0)
            except (ValueError, TypeError):
                qty = 0
            if qty <= 0:
                continue
            if qty > row["remaining"]:
                snack(self.page,
                      f"الكمية لـ '{row['product_name']}' تتجاوز "
                      f"المتاح ({row['remaining']}).",
                      kind="error")
                return
            reason_label = row["reason_dd"].value
            reason_type = (RETURN_REASON_DEFECT
                           if reason_label == "عيب مصنعي"
                           else RETURN_REASON_NORMAL)
            items.append({
                "product_code": row["product_code"],
                "product_name": row["product_name"],
                "quantity": qty,
                "price": row["price"],
                "reason_type": reason_type,
            })

        if not items:
            snack(self.page,
                  "أدخل كمية لإرجاع صنف واحد على الأقل.",
                  kind="warning")
            return

        total = sum(it["quantity"] * it["price"] for it in items)
        has_defect = any(it["reason_type"] == RETURN_REASON_DEFECT
                         for it in items)
        has_normal = any(it["reason_type"] == RETURN_REASON_NORMAL
                         for it in items)
        if has_defect and has_normal:
            summary_label = "مختلط (عيب + عادي)"
        elif has_defect:
            summary_label = "عيب مصنعي"
        else:
            summary_label = "مرتجع عادي"

        def do():
            try:
                ret = create_return(
                    invoice_id=self.current_invoice["id"],
                    items=items,
                    notes=(self.notes_input.value
                           if self.notes_input else "") or "",
                    created_by=self.user.get("cashier_code",
                                             self.user["username"]),
                )
            except Exception as ex:
                snack(self.page, str(ex), kind="error")
                return
            snack(self.page,
                  f"تم تسجيل مرتجع {ret.get('return_code') or ''} — "
                  f"{money_str(total, self.currency)}",
                  kind="success")

            try:
                self.page.close(self.dlg)
            except Exception:
                pass
            self.dlg = None
            self.current_invoice = None
            self.item_rows = []
            self._refresh()

        confirm_dialog(
            self.page, "تأكيد المرتجع",
            f"عدد الأصناف: {len(items)}\n"
            f"إجمالي الاسترداد: {money_str(total, self.currency)}\n"
            f"النوع: {summary_label}\n\n"
            f"• مرتجع عادي → يعود للمخزون القابل للبيع.\n"
            f"• عيب مصنعي → يُسجَّل كمعيب (لا يُضاف للمخزون القابل للبيع).",
            do, confirm_text="تنفيذ", danger=True)

    # ---------- Edit Return ----------
    def _edit_return(self, ret_row):
        ret = get_return(ret_row["id"])
        if not ret:
            return
        notes_field = text_field(
            "ملاحظات", value=ret.get("notes") or "", width=420,
            multiline=True)
        reason_controls = {}
        item_controls = []
        for it in ret.get("items", []):
            code = it["product_code"]
            current = it.get("reason_type") or RETURN_REASON_NORMAL
            dd = dropdown(
                "سبب الإرجاع",
                ["مرتجع عادي", "عيب مصنعي"],
                value=("عيب مصنعي" if current == RETURN_REASON_DEFECT
                       else "مرتجع عادي"),
                width=170)
            reason_controls[code] = dd
            item_controls.append(ft.Container(
                content=ft.Row([
                    ft.Column([
                        ft.Text(it["product_name"], color=TEXT_PRIMARY,
                                size=FS_SMALL, weight=ft.FontWeight.W_600,
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS),
                        ft.Text(
                            f"{code}  •  الكمية: {it['quantity']}  •  "
                            f"{money_str(it['price'], self.currency)}",
                            color=TEXT_MUTED, size=FS_TINY),
                    ], spacing=0, tight=True, expand=True),
                    dd,
                ], spacing=SP_SM,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=SP_SM, bgcolor=BG_INPUT,
                border_radius=RADIUS_SM))
        err = ft.Text("", color=DANGER, size=FS_SMALL, visible=False)

        def save(e):
            err.visible = False
            try:
                new_reasons = {}
                for code, dd in reason_controls.items():
                    new_reasons[code] = (
                        RETURN_REASON_DEFECT
                        if dd.value == "عيب مصنعي"
                        else RETURN_REASON_NORMAL)
                update_return(
                    ret_row["id"],
                    notes=notes_field.value or "",
                    per_item_reasons=new_reasons,
                    performed_by=self.user.get("cashier_code", ""))
            except Exception as ex:
                err.value = str(ex); err.visible = True
                err.update(); return
            self.page.close(dlg)
            self._refresh()
            snack(self.page, "تم تحديث المرتجع.", "success")

        def cancel(e=None): self.page.close(dlg)

        dlg = ft.AlertDialog(
            modal=True, bgcolor=BG_CARD,
            title=ft.Text(f"تعديل مرتجع {ret.get('return_code') or ''}",
                          color=TEXT_PRIMARY,
                          weight=ft.FontWeight.W_700, size=FS_SECTION),
            content=ft.Column([
                ft.Text(f"الفاتورة: #{ret.get('invoice_number') or '—'}",
                        color=TEXT_SECONDARY, size=FS_SMALL),
                ft.Text(f"العميل: {ret.get('customer_name') or '—'}",
                        color=TEXT_SECONDARY, size=FS_SMALL),
                ft.Text(
                    f"القيمة: "
                    f"{money_str(ret['total_refund'], self.currency)}",
                    color=SUCCESS, size=FS_SMALL,
                    weight=ft.FontWeight.W_700),
                divider(),
                section_title("الأصناف"),
                ft.Column(item_controls, spacing=SP_SM),
                divider(),
                notes_field, err,
            ], spacing=SP_SM, width=560, height=520,
                scroll=ft.ScrollMode.AUTO),
            actions=[ghost_button("إلغاء", cancel, width=110),
                     primary_button("حفظ", save, icon=ft.icons.CHECK,
                                    width=110)])
        self.page.open(dlg)

    # ---------- Delete Return ----------
    def _delete_return(self, ret_row):
        def do():
            try:
                delete_return(
                    ret_row["id"],
                    performed_by=self.user.get("cashier_code",
                                               self.user["username"]))
            except Exception as ex:
                snack(self.page, str(ex), "error"); return
            self._refresh()
            snack(self.page,
                  "تم حذف المرتجع واستعادة المخزون.", "success")
        confirm_dialog(
            self.page, "حذف المرتجع",
            f"حذف {ret_row.get('return_code') or ''}؟\n"
            f"سيتم استرجاع الكميات إلى المخزون وعكس قيمة الاسترداد.",
            do, confirm_text="حذف", danger=True)

    # ---------- Print Return (thermal) ----------
    def _print_return(self, ret_row):
        ret = get_return(ret_row["id"])
        if not ret:
            return
        open_thermal_return_preview(self.page, ret)


# --------------------------- SALES ---------------------------
class SalesView:
    def __init__(self, app, page, user):
        self.app = app; self.page = page; self.user = user
        self.currency = get_currency_symbol()
        self.tab = "pending"
        self.search = text_field("بحث…", prefix_icon=ft.icons.SEARCH,
                                 on_change=lambda e: self._refresh(),
                                 width=250)
        self.tabs_container = ft.Container()
        self.table = ft.Container(expand=True)

    def build(self):
        header = ft.Row([
            page_title("المبيعات", "قيد الدفع لا يُحسب ضمن مبيعات اليوم"),
            ft.Container(expand=True), self.search,
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=SP_MD)
        self.tabs_container = ft.Container(content=self._build_tabs())
        self._refresh()
        return ft.Column([
            header, ft.Container(height=SP_SM), self.tabs_container,
            ft.Container(height=SP_SM),
            card(ft.Column([self.table], expand=True, spacing=0),
                 padding=0, hover=False, expand=True),
        ], spacing=0, expand=True)

    def _build_tabs(self):
        row = ft.Row(spacing=SP_SM)
        for key, label in [("pending", "قيد الدفع"), ("paid", "تم الدفع")]:
            act = self.tab == key
            btn = ft.Container(
                content=ft.Text(label,
                                color=BG_BLACK if act else TEXT_PRIMARY,
                                size=FS_SMALL, weight=ft.FontWeight.W_700),
                bgcolor=ACCENT if act else BG_INPUT,
                border_radius=RADIUS_SM,
                padding=ft.padding.symmetric(horizontal=18, vertical=10),
                on_click=lambda e, k=key: self._switch_tab(k), ink=True)
            if not act:
                btn.on_hover = _hv_ghost
            row.controls.append(btn)
        return row

    def _switch_tab(self, key):
        self.tab = key
        self.tabs_container.content = self._build_tabs()
        self._refresh()
        try:
            self.tabs_container.update()
        except Exception:
            pass

    def _refresh(self):
        invoices = get_invoices(search=self.search.value or "",
                                status=self.tab)
        rows = []
        for inv in invoices:
            cashier_display = (inv.get("cashier_code")
                               or inv.get("cashier_name") or "—")
            rows.append([
                ft.Text(str(inv.get("invoice_number") or inv["id"]),
                        color=TEXT_PRIMARY, size=FS_SMALL,
                        weight=ft.FontWeight.W_700, max_lines=1),
                ft.Text(inv.get("customer_code") or "—", color=SUCCESS,
                        size=FS_SMALL, max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(inv.get("customer_name") or "—", color=TEXT_PRIMARY,
                        size=FS_SMALL, max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(money_str(inv["net_total"], self.currency),
                        color=TEXT_PRIMARY, size=FS_SMALL,
                        weight=ft.FontWeight.W_700, max_lines=1),
                ft.Text(inv["created_at"][:16], color=TEXT_SECONDARY,
                        size=FS_SMALL, max_lines=1),
                ft.Text(cashier_display, color=TEXT_SECONDARY,
                        size=FS_SMALL, max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS),
            ])

        def row_actions(inv):
            acts = [
                {"label": "تعديل", "icon": ft.icons.EDIT,
                 "handler": lambda i=inv: self._edit(i)},
                {"label": "طباعة حرارية", "icon": ft.icons.PRINT,
                 "handler": lambda i=inv: self._print(i)},
            ]
            if self.tab == "pending":
                acts.append({
                    "label": "تأكيد الدفع",
                    "icon": ft.icons.CHECK,
                    "color": SUCCESS,
                    "handler": lambda i=inv: self._mark_paid(i),
                })
            acts.append({
                "label": "حذف", "icon": ft.icons.DELETE,
                "handler": lambda i=inv: self._delete(i),
                "danger": True,
            })
            return acts

        self.table.content = data_table(
            self.page,
            [("الفاتورة", 65), ("كود العميل", 75), ("العميل", 105),
             ("الإجمالي", 85), ("التاريخ", 90), ("الكاشير", 80)],
            rows,
            ("لا فواتير قيد الدفع." if self.tab == "pending"
             else "لا فواتير مدفوعة."),
            raw_data=invoices, row_actions_builder=row_actions)
        try:
            self.table.update()
        except Exception:
            pass

    def _mark_paid(self, inv):
        def do():
            update_invoice(inv["id"], status="paid")
            self._refresh()
            snack(self.page,
                  "تم الدفع. انتقلت الفاتورة إلى قيد الشحن.",
                  kind="success")
        confirm_dialog(self.page, "هل تم استلام الدفع؟",
                       f"الفاتورة #{inv.get('invoice_number', inv['id'])} "
                       f"— {money_str(inv['net_total'], self.currency)}",
                       do, confirm_text="تم الدفع", danger=False)

    def _print(self, inv):
        full = get_invoice(inv["id"])
        if full is None:
            return
        full = enrich_invoice_for_print(full)
        open_thermal_preview(self.page, full)

    def _edit(self, inv):
        full = get_invoice(inv["id"])
        if full is None:
            return
        name = text_field("العميل", value=full.get("customer_name") or "",
                          width=300)
        phone = text_field("الهاتف", value=full.get("customer_phone") or "",
                           width=300)
        address = text_field("العنوان",
                             value=full.get("customer_address") or "",
                             width=400)
        gov = text_field("المحافظة",
                         value=full.get("customer_governorate") or "",
                         width=200)
        disc = text_field("الخصم", value=f"{full.get('discount', 0):.2f}",
                          width=200, keyboard_type=ft.KeyboardType.NUMBER)
        err = ft.Text("", color=DANGER, size=FS_SMALL, visible=False)

        def save(e):
            err.visible = False
            try:
                update_invoice(full["id"],
                               customer_name=name.value,
                               customer_phone=phone.value,
                               customer_address=address.value,
                               customer_governorate=gov.value,
                               discount=disc.value)
            except Exception as ex:
                err.value = str(ex); err.visible = True; err.update(); return
            self.page.close(dlg); self._refresh()

        def cancel(e=None): self.page.close(dlg)

        dlg = ft.AlertDialog(
            modal=True, bgcolor=BG_CARD,
            title=ft.Text(f"تعديل #{full.get('invoice_number', full['id'])}",
                          color=TEXT_PRIMARY, weight=ft.FontWeight.W_700,
                          size=FS_SECTION),
            content=ft.Column(
                [name, ft.Row([phone, gov], spacing=SP_MD), address,
                 disc, err], spacing=SP_SM, width=440),
            actions=[ghost_button("إلغاء", cancel, width=110),
                     primary_button("حفظ", save, icon=ft.icons.CHECK,
                                    width=110)])
        self.page.open(dlg)

    def _delete(self, inv):
        def do():
            delete_invoice(inv["id"], performed_by=self.user.get(
                "cashier_code", self.user["username"]))
            self._refresh()
            snack(self.page, "تم الحذف.", kind="success")
        confirm_dialog(self.page, "حذف الفاتورة",
                       f"حذف #{inv.get('invoice_number', inv['id'])}؟",
                       do, confirm_text="حذف", danger=True)


# --------------------------- SHIPPING ---------------------------
class ShippingView:
    def __init__(self, app, page, user):
        self.app = app; self.page = page; self.user = user
        self.currency = get_currency_symbol()
        self.tab = "pending"
        self.search = text_field("بحث…", prefix_icon=ft.icons.SEARCH,
                                 on_change=lambda e: self._refresh(),
                                 width=250)
        self.tabs_container = ft.Container()
        self.table = ft.Container(expand=True)
        self.print_all_btn = primary_button(
            "طباعة الكل", self._print_all, icon=ft.icons.PRINT, width=180)

    def build(self):
        header = ft.Row([
            page_title("الشحن", "قيد الشحن / تم الشحن"),
            ft.Container(expand=True), self.search,
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=SP_MD)
        self.tabs_container = ft.Container(content=self._build_tabs())
        self._refresh()
        return ft.Column([
            header, ft.Container(height=SP_SM), self.tabs_container,
            ft.Container(height=SP_SM),
            card(ft.Column([self.table], expand=True, spacing=0),
                 padding=0, hover=False, expand=True),
            ft.Container(height=SP_SM),
            ft.Row([ft.Container(expand=True), self.print_all_btn],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ], spacing=0, expand=True)

    def _build_tabs(self):
        row = ft.Row(spacing=SP_SM)
        for key, label in [("pending", "قيد الشحن"), ("shipped", "تم الشحن")]:
            act = self.tab == key
            btn = ft.Container(
                content=ft.Text(label,
                                color=BG_BLACK if act else TEXT_PRIMARY,
                                size=FS_SMALL, weight=ft.FontWeight.W_700),
                bgcolor=ACCENT if act else BG_INPUT,
                border_radius=RADIUS_SM,
                padding=ft.padding.symmetric(horizontal=18, vertical=10),
                on_click=lambda e, k=key: self._switch_tab(k), ink=True)
            if not act:
                btn.on_hover = _hv_ghost
            row.controls.append(btn)
        return row

    def _switch_tab(self, key):
        self.tab = key
        self.tabs_container.content = self._build_tabs()
        self._refresh()
        try:
            self.tabs_container.update()
        except Exception:
            pass

    def _filtered_invoices(self):
        invoices = (get_pending_shipping() if self.tab == "pending"
                    else get_shipped())
        term = (self.search.value or "").strip().lower()
        if term:
            invoices = [i for i in invoices
                        if term in (i.get("customer_name") or "").lower()
                        or term in (i.get("customer_phone") or "").lower()
                        or term in (i.get("customer_code") or "").lower()
                        or term in str(i.get("invoice_number", ""))]
        return invoices

    def _refresh(self):
        invoices = self._filtered_invoices()
        rows = []
        for inv in invoices:
            rows.append([
                ft.Text(str(inv.get("invoice_number") or inv["id"]),
                        color=TEXT_PRIMARY, size=FS_SMALL,
                        weight=ft.FontWeight.W_700, max_lines=1),
                ft.Text(inv.get("customer_name") or "—", color=TEXT_PRIMARY,
                        size=FS_SMALL, max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(inv.get("customer_phone") or "—",
                        color=TEXT_SECONDARY, size=FS_SMALL, max_lines=1),
                ft.Text(inv.get("customer_governorate") or "—",
                        color=TEXT_SECONDARY, size=FS_SMALL, max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text((inv.get("customer_address") or "—")[:30],
                        color=TEXT_MUTED, size=FS_SMALL, max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS),
                (ft.Text(inv.get("waybill_number") or "—", color=SUCCESS,
                         size=FS_SMALL, weight=ft.FontWeight.W_700,
                         max_lines=1)
                 if self.tab == "shipped"
                 else ft.Text("—", color=TEXT_MUTED, size=FS_SMALL)),
            ])

        def row_actions(inv):
            acts = [
                {"label": "تعديل", "icon": ft.icons.EDIT,
                 "handler": lambda i=inv: self._edit(i)},
                {"label": "طباعة A4", "icon": ft.icons.PRINT,
                 "handler": lambda i=inv: self._print(i)},
            ]
            if self.tab == "pending":
                acts.append({
                    "label": "تم الشحن (إدخال البوليصة)",
                    "icon": ft.icons.CHECK,
                    "color": SUCCESS,
                    "handler": lambda i=inv: self._waybill(i),
                })
            acts.append({
                "label": "حذف", "icon": ft.icons.DELETE,
                "handler": lambda i=inv: self._delete(i),
                "danger": True,
            })
            return acts

        self.table.content = data_table(
            self.page,
            [("الفاتورة", 60), ("العميل", 90), ("الهاتف", 75),
             ("المحافظة", 70), ("العنوان", 105),
             ("البوليصة" if self.tab == "shipped" else "—", 75)],
            rows,
            ("لا شحنات قيد الانتظار." if self.tab == "pending"
             else "لا شحنات تم شحنها."),
            raw_data=invoices, row_actions_builder=row_actions)
        try:
            self.table.update()
        except Exception:
            pass

    def _waybill(self, inv):
        full = get_invoice(inv["id"])
        info_lines = []
        if full:
            info_lines = [
                ft.Text(f"العميل: {full.get('customer_name') or '—'}",
                        color=TEXT_PRIMARY, size=FS_SMALL,
                        weight=ft.FontWeight.W_600),
                ft.Text(f"الهاتف: {full.get('customer_phone') or '—'}",
                        color=TEXT_SECONDARY, size=FS_SMALL),
                ft.Text(f"العنوان: {full.get('customer_address') or '—'}",
                        color=TEXT_SECONDARY, size=FS_SMALL),
                ft.Text(f"الإجمالي: "
                        f"{money_str(full['net_total'], self.currency)}",
                        color=TEXT_PRIMARY, size=FS_SMALL,
                        weight=ft.FontWeight.W_700),
            ]
        w = text_field("الرجاء إدخال رقم البوليصة *",
                       width=320, autofocus=True)
        err = ft.Text("", color=DANGER, size=FS_SMALL, visible=False)

        def save(e):
            err.visible = False
            try:
                v = (w.value or "").strip()
                if not v:
                    raise ValueError("رقم البوليصة مطلوب.")
                update_invoice(inv["id"], waybill_number=v)
            except Exception as ex:
                err.value = str(ex); err.visible = True; err.update(); return
            self.page.close(dlg); self._refresh()
            snack(self.page, "تم الشحن. انتقلت الفاتورة إلى تم الشحن.",
                  kind="success")

        def cancel(e=None): self.page.close(dlg)

        content_col = ft.Column(
            info_lines + [ft.Container(height=SP_SM), w, err],
            spacing=SP_XS, width=320)

        dlg = ft.AlertDialog(
            modal=True, bgcolor=BG_CARD,
            title=ft.Text("إدخال رقم البوليصة",
                          color=TEXT_PRIMARY, weight=ft.FontWeight.W_700,
                          size=FS_SECTION),
            content=content_col,
            actions=[ghost_button("إلغاء", cancel, width=110),
                     primary_button("حفظ وشحن", save, icon=ft.icons.CHECK,
                                    width=150)])
        self.page.open(dlg)

    def _print(self, inv):
        full = get_invoice(inv["id"])
        if full is None:
            return
        full = enrich_invoice_for_print(full)
        open_a4_invoice_preview(self.page, full)

    def _print_all(self, e):
        invoices = self._filtered_invoices()
        if not invoices:
            snack(self.page, "لا بيانات للطباعة.", kind="warning")
            return
        if self.tab == "pending":
            headers = ["مسلسل", "العميل", "الهاتف", "العنوان",
                       "رقم الفاتورة"]
            rows = []
            for i, inv in enumerate(invoices, 1):
                rows.append([
                    str(i),
                    inv.get("customer_name") or "—",
                    inv.get("customer_phone") or "—",
                    inv.get("customer_address") or "—",
                    str(inv.get("invoice_number") or inv["id"]),
                ])
            title = "شحنات قيد الانتظار"
            base = "shipping_pending"
        else:
            headers = ["مسلسل", "العميل", "الهاتف", "العنوان",
                       "البوليصة", "رقم الفاتورة"]
            rows = []
            for i, inv in enumerate(invoices, 1):
                rows.append([
                    str(i),
                    inv.get("customer_name") or "—",
                    inv.get("customer_phone") or "—",
                    inv.get("customer_address") or "—",
                    inv.get("waybill_number") or "—",
                    str(inv.get("invoice_number") or inv["id"]),
                ])
            title = "شحنات تم شحنها"
            base = "shipping_shipped"
        open_report_preview(
            self.page, title, headers, rows, [],
            "shipping", base)

    def _edit(self, inv):
        full = get_invoice(inv["id"])
        if not full:
            return
        name = text_field("العميل", value=full.get("customer_name") or "",
                          width=300)
        phone = text_field("الهاتف", value=full.get("customer_phone") or "",
                           width=300)
        address = text_field("العنوان",
                             value=full.get("customer_address") or "",
                             width=400)
        gov = text_field("المحافظة",
                         value=full.get("customer_governorate") or "",
                         width=200)
        err = ft.Text("", color=DANGER, size=FS_SMALL, visible=False)

        def save(e):
            err.visible = False
            try:
                update_invoice(full["id"],
                               customer_name=name.value,
                               customer_phone=phone.value,
                               customer_address=address.value,
                               customer_governorate=gov.value)
            except Exception as ex:
                err.value = str(ex); err.visible = True; err.update(); return
            self.page.close(dlg); self._refresh()

        def cancel(e=None): self.page.close(dlg)

        dlg = ft.AlertDialog(
            modal=True, bgcolor=BG_CARD,
            title=ft.Text(f"تعديل بيانات الشحن "
                          f"#{full.get('invoice_number', full['id'])}",
                          color=TEXT_PRIMARY, weight=ft.FontWeight.W_700,
                          size=FS_SECTION),
            content=ft.Column(
                [name, ft.Row([phone, gov], spacing=SP_MD), address, err],
                spacing=SP_SM, width=440),
            actions=[ghost_button("إلغاء", cancel, width=110),
                     primary_button("حفظ", save, icon=ft.icons.CHECK,
                                    width=110)])
        self.page.open(dlg)

    def _delete(self, inv):
        def do():
            delete_invoice(inv["id"], performed_by=self.user.get(
                "cashier_code", self.user["username"]))
            self._refresh()
            snack(self.page, "تم الحذف.", kind="success")
        confirm_dialog(self.page, "حذف الفاتورة",
                       f"حذف #{inv.get('invoice_number', inv['id'])}؟",
                       do, confirm_text="حذف", danger=True)


# --------------------------- INVENTORY ---------------------------
class InventoryView:
    def __init__(self, app, page, user):
        self.app = app; self.page = page; self.user = user
        self.currency = get_currency_symbol()
        self.search = text_field("بحث…", prefix_icon=ft.icons.SEARCH,
                                 on_change=lambda e: self._refresh(),
                                 width=250)
        self.table = ft.Container(expand=True)

    def build(self):
        header = ft.Row([
            page_title("المخزون", "كتالوج المنتجات"),
            ft.Container(expand=True), self.search,
            primary_button("إضافة منتج", self._add,
                           icon=ft.icons.ADD, width=160),
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=SP_MD)
        self._refresh()
        return ft.Column([
            header, ft.Container(height=SP_SM),
            card(ft.Column([self.table], expand=True, spacing=0),
                 padding=0, hover=False, expand=True),
        ], spacing=0, expand=True)

    def _refresh(self):
        products = get_all_products(self.search.value or "")
        rows = []
        for p in products:
            low = p["min_limit"] > 0 and p["stock_qty"] <= p["min_limit"]
            rows.append([
                ft.Text(p["code"], color=TEXT_SECONDARY, size=FS_SMALL,
                        max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(p["name"], color=TEXT_PRIMARY, size=FS_SMALL,
                        weight=ft.FontWeight.W_600, max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(p.get("supplier") or "—", color=TEXT_MUTED,
                        size=FS_SMALL, max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(str(p["stock_qty"]),
                        color=DANGER if low else TEXT_PRIMARY,
                        size=FS_SMALL, weight=ft.FontWeight.W_700),
                ft.Text(str(p.get("defect_qty", 0) or 0),
                        color=WARNING if p.get("defect_qty", 0) else TEXT_MUTED,
                        size=FS_SMALL),
                ft.Text(money_str(p["wholesale_price"], self.currency),
                        color=TEXT_PRIMARY, size=FS_SMALL, max_lines=1),
            ])

        def row_actions(p):
            return [
                {"label": "تعديل", "icon": ft.icons.EDIT,
                 "handler": lambda p=p: self._edit(p)},
                {"label": "طباعة A4", "icon": ft.icons.PRINT,
                 "handler": lambda p=p: self._print(p)},
                {"label": "حذف", "icon": ft.icons.DELETE,
                 "handler": lambda p=p: self._delete(p),
                 "danger": True},
            ]

        self.table.content = data_table(
            self.page,
            [("الكود", 70), ("الاسم", 130), ("المورد", 90),
             ("المخزون", 60), ("عيوب", 50), ("سعر البيع", 85)],
            rows, "لا منتجات.", raw_data=products,
            row_actions_builder=row_actions)
        try:
            self.table.update()
        except Exception:
            pass

    def _add(self, e=None): self._form(None)
    def _edit(self, p): self._form(p)

    def _form(self, p):
        is_edit = p is not None
        code = text_field("الكود *", value=p["code"] if is_edit else "",
                          width=300)
        name = text_field("الاسم *", value=p["name"] if is_edit else "",
                          width=400)
        supplier = text_field("المورد",
                              value=(p.get("supplier") or "") if is_edit
                              else "", width=400)
        err = ft.Text("", color=DANGER, size=FS_SMALL, visible=False)

        def save(e):
            err.visible = False
            try:
                if is_edit:
                    update_product(p["id"], code.value, name.value,
                                   supplier.value)
                else:
                    add_product(code.value, name.value, supplier.value)
            except Exception as ex:
                err.value = str(ex); err.visible = True; err.update(); return
            self.page.close(dlg); self._refresh()

        def cancel(e=None): self.page.close(dlg)

        dlg = ft.AlertDialog(
            modal=True, bgcolor=BG_CARD,
            title=ft.Text("تعديل منتج" if is_edit else "إضافة منتج",
                          color=TEXT_PRIMARY, weight=ft.FontWeight.W_700,
                          size=FS_SECTION),
            content=ft.Column([code, name, supplier, err],
                              spacing=SP_SM, width=420),
            actions=[ghost_button("إلغاء", cancel, width=110),
                     primary_button("حفظ", save, icon=ft.icons.CHECK,
                                    width=110)])
        self.page.open(dlg)

    def _print(self, p):
        pairs = [
            ("كود المنتج", p["code"]), ("اسم المنتج", p["name"]),
            ("المورد", p.get("supplier") or "—"),
            ("المخزون الحالي", p["stock_qty"]),
            ("الكمية المعيبة", p.get("defect_qty", 0) or 0),
            ("الحد الأدنى", p.get("min_limit", 0)),
            ("سعر البيع", f"{p['wholesale_price']:.2f} ج.م"),
        ]
        open_report_preview(
            self.page, "بطاقة منتج", ["البند", "القيمة"],
            [[k, v] for k, v in pairs], [],
            "products", f"product_{p['code']}")

    def _delete(self, p):
        def do():
            delete_product(p["id"]); self._refresh()
            snack(self.page, "تم الحذف.", kind="success")
        confirm_dialog(self.page, "حذف المنتج", f"حذف '{p['name']}'؟",
                       do, confirm_text="حذف", danger=True)


# --------------------------- PURCHASES ---------------------------
class PurchasesView:
    def __init__(self, app, page, user):
        self.app = app; self.page = page; self.user = user
        self.currency = get_currency_symbol()
        products = get_all_products()
        self.product_dd = keyed_dropdown(
            "المنتج", [(p["code"], p["name"]) for p in products], width=220,
            on_change=self._on_product_change)
        self.name_f = text_field("اسم المنتج", read_only=True, width=170)
        suppliers = get_all_suppliers()
        self.supplier_dd = keyed_dropdown(
            "المورد *",
            [(s["name"], s["name"]) for s in suppliers],
            width=160)
        self.qty_f = text_field("الكمية", width=90,
                                keyboard_type=ft.KeyboardType.NUMBER)
        self.cost_f = text_field("سعر التكلفة", width=110,
                                 keyboard_type=ft.KeyboardType.NUMBER)
        self.sell_f = text_field("سعر البيع", width=110,
                                 keyboard_type=ft.KeyboardType.NUMBER)
        self.table = ft.Container(expand=True)

    def _refresh_suppliers(self):
        try:
            suppliers = get_all_suppliers()
            self.supplier_dd.options = [
                ft.dropdown.Option(key=s["name"], text=s["name"])
                for s in suppliers]
            try:
                self.supplier_dd.update()
            except Exception:
                pass
        except Exception:
            pass

    def _on_product_change(self, e):
        code = self.product_dd.value
        if code:
            p = get_product_by_code(code)
            if p:
                self.name_f.value = p["name"]
                self.sell_f.value = (f"{p['wholesale_price']:.2f}"
                                     if p["wholesale_price"] else "")
                self.cost_f.value = (f"{p['cost_price']:.2f}"
                                     if p["cost_price"] else "")
                if p.get("supplier"):
                    self.supplier_dd.value = p["supplier"]
        else:
            self.name_f.value = ""
            self.sell_f.value = ""; self.cost_f.value = ""
        for f in (self.name_f, self.sell_f, self.cost_f,
                  self.supplier_dd):
            try:
                f.update()
            except Exception:
                pass

    def build(self):
        form = card(ft.Column([
            section_title("تسجيل شراء"), ft.Container(height=SP_SM),
            ft.Row([self.product_dd, self.name_f, self.supplier_dd,
                    self.qty_f, self.cost_f, self.sell_f,
                    primary_button("حفظ", self._add, icon=ft.icons.SAVE,
                                   width=120)],
                   spacing=SP_MD,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER,
                   wrap=True),
        ], spacing=0), padding=SP_MD, hover=False)
        self._refresh()
        return ft.Column([
            page_title("المشتريات", "تسجيل المشتريات من الموردين"),
            ft.Container(height=SP_SM), form, ft.Container(height=SP_SM),
            card(ft.Column([self.table], expand=True, spacing=0),
                 padding=0, hover=False, expand=True),
        ], spacing=0, expand=True)

    def _add(self, e):
        code = self.product_dd.value
        if not code:
            snack(self.page, "اختر منتجاً.", kind="warning"); return
        supplier = self.supplier_dd.value
        if not supplier:
            snack(self.page, "اختر مورداً.", kind="warning"); return
        try:
            create_purchase(code, self.qty_f.value, self.cost_f.value,
                            self.sell_f.value, supplier=supplier)
        except Exception as ex:
            snack(self.page, str(ex), kind="error"); return
        for f in (self.product_dd, self.name_f, self.supplier_dd,
                  self.qty_f, self.cost_f, self.sell_f):
            try:
                f.value = None if f in (self.product_dd, self.supplier_dd) \
                    else ""
                f.update()
            except Exception:
                pass
        self._refresh()
        snack(self.page, "تم تسجيل الشراء.", kind="success")

    def _refresh(self):
        purchases = get_all_purchases()
        rows = []
        for p in purchases:
            rows.append([
                ft.Text(p["created_at"][:10], color=TEXT_SECONDARY,
                        size=FS_SMALL),
                ft.Text(p["product_name"], color=TEXT_PRIMARY,
                        size=FS_SMALL, weight=ft.FontWeight.W_600,
                        max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(p["supplier"] or "—", color=TEXT_MUTED,
                        size=FS_SMALL, max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(str(p["quantity"]), color=TEXT_PRIMARY,
                        size=FS_SMALL),
                ft.Text(money_str(p["purchase_price"], self.currency),
                        color=TEXT_SECONDARY, size=FS_SMALL, max_lines=1),
                ft.Text(money_str(p["selling_price"], self.currency),
                        color=TEXT_PRIMARY, size=FS_SMALL, max_lines=1),
                ft.Text(money_str(p["total_cost"], self.currency),
                        color=TEXT_PRIMARY, size=FS_SMALL,
                        weight=ft.FontWeight.W_700, max_lines=1),
            ])

        def row_actions(p):
            return [
                {"label": "تعديل", "icon": ft.icons.EDIT,
                 "handler": lambda p=p: self._edit(p)},
                {"label": "طباعة A4", "icon": ft.icons.PRINT,
                 "handler": lambda p=p: self._print(p)},
                {"label": "حذف", "icon": ft.icons.DELETE,
                 "handler": lambda p=p: self._delete(p),
                 "danger": True},
            ]

        self.table.content = data_table(
            self.page,
            [("التاريخ", 70), ("المنتج", 110), ("المورد", 85),
             ("الكمية", 55), ("سعر الشراء", 70),
             ("سعر البيع", 70), ("الإجمالي", 80)],
            rows, "لا مشتريات.", raw_data=purchases,
            row_actions_builder=row_actions)
        try:
            self.table.update()
        except Exception:
            pass

    def _edit(self, p):
        dd = keyed_dropdown(
            "المنتج", [(x["code"], x["name"]) for x in get_all_products()],
            value=p["product_code"], width=280)
        suppliers = get_all_suppliers()
        sdd = keyed_dropdown(
            "المورد *",
            [(s["name"], s["name"]) for s in suppliers],
            value=(p.get("supplier") or None), width=220)
        qty = text_field("الكمية", value=str(p["quantity"]), width=140,
                         keyboard_type=ft.KeyboardType.NUMBER)
        cost = text_field("سعر التكلفة",
                          value=f"{p['purchase_price']:.2f}", width=160,
                          keyboard_type=ft.KeyboardType.NUMBER)
        price = text_field("سعر البيع",
                           value=f"{p['selling_price']:.2f}", width=160,
                           keyboard_type=ft.KeyboardType.NUMBER)
        err = ft.Text("", color=DANGER, size=FS_SMALL, visible=False)

        def save(e):
            err.visible = False
            try:
                if not sdd.value:
                    raise ValueError("اختر مورداً.")
                update_purchase(p["id"], dd.value, qty.value,
                                cost.value, price.value,
                                supplier=sdd.value)
            except Exception as ex:
                err.value = str(ex); err.visible = True; err.update(); return
            self.page.close(dlg); self._refresh()

        def cancel(e=None): self.page.close(dlg)

        dlg = ft.AlertDialog(
            modal=True, bgcolor=BG_CARD,
            title=ft.Text("تعديل شراء", color=TEXT_PRIMARY,
                          weight=ft.FontWeight.W_700, size=FS_SECTION),
            content=ft.Column(
                [dd, sdd,
                 ft.Row([qty, cost, price], spacing=SP_MD), err],
                spacing=SP_SM, width=480),
            actions=[ghost_button("إلغاء", cancel, width=110),
                     primary_button("حفظ", save, icon=ft.icons.CHECK,
                                    width=110)])
        self.page.open(dlg)

    def _print(self, p):
        pairs = [
            ("رقم العملية", p["id"]), ("التاريخ", p["created_at"]),
            ("المنتج", p["product_name"]),
            ("كود المنتج", p["product_code"]),
            ("المورد", p.get("supplier") or "—"),
            ("الكمية", p["quantity"]),
            ("سعر الشراء", f"{p['purchase_price']:.2f} ج.م"),
            ("سعر البيع", f"{p['selling_price']:.2f} ج.م"),
            ("الإجمالي", f"{p['total_cost']:.2f} ج.م"),
        ]
        open_report_preview(
            self.page, "تفاصيل شراء", ["البند", "القيمة"],
            [[k, v] for k, v in pairs], [],
            "purchases", f"purchase_{p['id']}")

    def _delete(self, p):
        def do():
            delete_purchase(p["id"]); self._refresh()
            snack(self.page, "تم الحذف.", kind="success")
        confirm_dialog(self.page, "حذف عملية شراء",
                       f"حذف شراء '{p['product_name']}'؟ "
                       "ستُخصم الكمية من المخزون.",
                       do, confirm_text="حذف", danger=True)


# --------------------------- SUPPLIERS ---------------------------
class SuppliersView:
    def __init__(self, app, page, user):
        self.app = app; self.page = page; self.user = user
        self.search = text_field("بحث…", prefix_icon=ft.icons.SEARCH,
                                 on_change=lambda e: self._refresh(),
                                 width=250)
        self.table = ft.Container(expand=True)

    def build(self):
        header = ft.Row([
            page_title("الموردون", "دليل الموردين"),
            ft.Container(expand=True), self.search,
            primary_button("إضافة مورد", self._add, icon=ft.icons.ADD,
                           width=160),
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=SP_MD)
        self._refresh()
        return ft.Column([
            header, ft.Container(height=SP_SM),
            card(ft.Column([self.table], expand=True, spacing=0),
                 padding=0, hover=False, expand=True),
        ], spacing=0, expand=True)

    def _refresh(self):
        suppliers = get_all_suppliers(self.search.value or "")
        rows = []
        for s in suppliers:
            rows.append([
                ft.Text(s["name"], color=TEXT_PRIMARY, size=FS_SMALL,
                        weight=ft.FontWeight.W_600, max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(s["phone"] or "—", color=TEXT_SECONDARY,
                        size=FS_SMALL, max_lines=1),
                ft.Text(s["address"] or "—", color=TEXT_SECONDARY,
                        size=FS_SMALL, max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text((s["notes"] or "—")[:50], color=TEXT_MUTED,
                        size=FS_SMALL, max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS),
            ])

        def row_actions(s):
            return [
                {"label": "تعديل", "icon": ft.icons.EDIT,
                 "handler": lambda s=s: self._edit(s)},
                {"label": "طباعة A4", "icon": ft.icons.PRINT,
                 "handler": lambda s=s: self._print(s)},
                {"label": "حذف", "icon": ft.icons.DELETE,
                 "handler": lambda s=s: self._delete(s),
                 "danger": True},
            ]

        self.table.content = data_table(
            self.page,
            [("الاسم", 120), ("الهاتف", 95), ("العنوان", 130),
             ("ملاحظات", 140)],
            rows, "لا موردون.", raw_data=suppliers,
            row_actions_builder=row_actions)
        try:
            self.table.update()
        except Exception:
            pass

    def _add(self, e=None): self._form(None)
    def _edit(self, s): self._form(s)

    def _form(self, s):
        is_edit = s is not None
        name = text_field("الاسم *", value=s["name"] if is_edit else "",
                          width=400)
        phone = text_field("الهاتف", value=s["phone"] if is_edit else "",
                           width=220)
        address = text_field("العنوان", value=s["address"] if is_edit else "",
                             width=220)
        notes = text_field("ملاحظات", value=s["notes"] if is_edit else "",
                           multiline=True, width=440)
        err = ft.Text("", color=DANGER, size=FS_SMALL, visible=False)

        def save(e):
            err.visible = False
            try:
                if is_edit:
                    update_supplier(s["id"], name.value, phone.value,
                                    address.value, notes.value)
                else:
                    add_supplier(name.value, phone.value, address.value,
                                 notes.value)
            except Exception as ex:
                err.value = str(ex); err.visible = True; err.update(); return
            self.page.close(dlg); self._refresh()

        def cancel(e=None): self.page.close(dlg)

        dlg = ft.AlertDialog(
            modal=True, bgcolor=BG_CARD,
            title=ft.Text("تعديل مورد" if is_edit else "إضافة مورد",
                          color=TEXT_PRIMARY, weight=ft.FontWeight.W_700,
                          size=FS_SECTION),
            content=ft.Column(
                [name, ft.Row([phone, address], spacing=SP_MD), notes, err],
                spacing=SP_SM, width=460),
            actions=[ghost_button("إلغاء", cancel, width=110),
                     primary_button("حفظ", save, icon=ft.icons.CHECK,
                                    width=110)])
        self.page.open(dlg)

    def _print(self, s):
        pairs = [
            ("الاسم", s["name"]),
            ("الهاتف", s.get("phone") or "—"),
            ("العنوان", s.get("address") or "—"),
            ("ملاحظات", s.get("notes") or "—"),
        ]
        open_report_preview(
            self.page, "بطاقة مورد", ["البند", "القيمة"],
            [[k, v] for k, v in pairs], [],
            "suppliers", f"supplier_{s['id']}")

    def _delete(self, s):
        def do():
            delete_supplier(s["id"]); self._refresh()
            snack(self.page, "تم الحذف.", kind="success")
        confirm_dialog(self.page, "حذف المورد", f"حذف '{s['name']}'؟",
                       do, confirm_text="حذف", danger=True)


# --------------------------- EXPENSES ---------------------------
class ExpensesView:
    def __init__(self, app, page, user):
        self.app = app; self.page = page; self.user = user
        self.currency = get_currency_symbol()
        self.total_text = ft.Text(money_str(0, self.currency),
                                  color=TEXT_PRIMARY, size=20,
                                  weight=ft.FontWeight.W_900)
        self.table = ft.Container(expand=True)

    def build(self):
        header = ft.Row([
            page_title("المصروفات", "المصاريف التشغيلية"),
            ft.Container(expand=True),
            primary_button("إضافة مصروف", self._add, icon=ft.icons.ADD,
                           width=160),
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER)
        self._refresh()
        return ft.Column([
            header, ft.Container(height=SP_SM),
            card(ft.Row([ft.Column([
                ft.Text("الإجمالي", color=TEXT_SECONDARY, size=FS_SMALL),
                self.total_text], spacing=2)],
                vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=SP_SM, hover=False),
            ft.Container(height=SP_SM),
            card(ft.Column([self.table], expand=True, spacing=0),
                 padding=0, hover=False, expand=True),
        ], spacing=0, expand=True)

    def _refresh(self):
        expenses = get_expenses()
        self.total_text.value = money_str(get_total_expenses(), self.currency)
        rows = []
        for ex in expenses:
            rows.append([
                ft.Text(ex["date"], color=TEXT_SECONDARY, size=FS_SMALL),
                ft.Text(ex["category"], color=TEXT_PRIMARY, size=FS_SMALL,
                        weight=ft.FontWeight.W_600, max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(money_str(ex["amount"], self.currency),
                        color=TEXT_PRIMARY, size=FS_SMALL,
                        weight=ft.FontWeight.W_700, max_lines=1),
                ft.Text(ex["notes"] or "—", color=TEXT_MUTED,
                        size=FS_SMALL, max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS),
            ])

        def row_actions(ex):
            return [
                {"label": "تعديل", "icon": ft.icons.EDIT,
                 "handler": lambda ex=ex: self._edit(ex)},
                {"label": "طباعة A4", "icon": ft.icons.PRINT,
                 "handler": lambda ex=ex: self._print(ex)},
                {"label": "حذف", "icon": ft.icons.DELETE,
                 "handler": lambda ex=ex: self._delete(ex),
                 "danger": True},
            ]

        self.table.content = data_table(
            self.page,
            [("التاريخ", 80), ("الفئة", 120), ("المبلغ", 90),
             ("ملاحظات", 200)],
            rows, "لا مصروفات.", raw_data=expenses,
            row_actions_builder=row_actions)
        try:
            self.total_text.update()
            self.table.update()
        except Exception:
            pass

    def _add(self, e=None): self._form(None)
    def _edit(self, ex): self._form(ex)

    def _form(self, ex):
        is_edit = ex is not None
        cats = ["إيجار", "مرافق", "رواتب", "مواصلات", "مستلزمات",
                "صيانة", "تسويق", "أخرى"]
        for c in get_expense_categories():
            if c not in cats:
                cats.append(c)
        cat = dropdown("الفئة *", cats,
                       value=(ex["category"] if is_edit else cats[0]),
                       width=220)
        amt = text_field("المبلغ *",
                         value=f"{ex['amount']:.2f}" if is_edit else "0.00",
                         width=200, keyboard_type=ft.KeyboardType.NUMBER)
        d = text_field("التاريخ",
                       value=(ex["date"] if is_edit
                              else date.today().isoformat()), width=200)
        notes = text_field("ملاحظات", value=ex["notes"] if is_edit else "",
                           multiline=True, width=420)
        err = ft.Text("", color=DANGER, size=FS_SMALL, visible=False)

        def save(e):
            err.visible = False
            try:
                if is_edit:
                    update_expense(ex["id"], cat.value, amt.value,
                                   notes.value, d.value)
                else:
                    add_expense(cat.value, amt.value, notes.value, d.value)
            except Exception as ex2:
                err.value = str(ex2); err.visible = True; err.update(); return
            self.page.close(dlg); self._refresh()

        def cancel(e=None): self.page.close(dlg)

        dlg = ft.AlertDialog(
            modal=True, bgcolor=BG_CARD,
            title=ft.Text("تعديل مصروف" if is_edit else "إضافة مصروف",
                          color=TEXT_PRIMARY, weight=ft.FontWeight.W_700,
                          size=FS_SECTION),
            content=ft.Column([ft.Row([cat, amt, d], spacing=SP_MD),
                               notes, err], spacing=SP_SM, width=460),
            actions=[ghost_button("إلغاء", cancel, width=110),
                     primary_button("حفظ", save, icon=ft.icons.CHECK,
                                    width=110)])
        self.page.open(dlg)

    def _print(self, ex):
        pairs = [
            ("رقم المصروف", ex["id"]), ("التاريخ", ex["date"]),
            ("الفئة", ex["category"]),
            ("المبلغ", f"{ex['amount']:.2f} ج.م"),
            ("ملاحظات", ex.get("notes") or "—"),
        ]
        open_report_preview(
            self.page, "تفاصيل مصروف", ["البند", "القيمة"],
            [[k, v] for k, v in pairs], [],
            "expenses", f"expense_{ex['id']}")

    def _delete(self, ex):
        def do():
            delete_expense(ex["id"]); self._refresh()
            snack(self.page, "تم الحذف.", kind="success")
        confirm_dialog(self.page, "حذف المصروف", f"حذف '{ex['category']}'؟",
                       do, confirm_text="حذف", danger=True)


# --------------------------- REPORTS ---------------------------
class ReportsView:
    def __init__(self, app, page, user):
        self.app = app; self.page = page; self.user = user
        self.currency = get_currency_symbol()
        today = date.today()
        self.date_from = text_field(
            "من", value=(today - timedelta(days=30)).isoformat(),
            width=140, on_change=lambda e: self._refresh())
        self.date_to = text_field("إلى", value=today.isoformat(), width=140,
                                  on_change=lambda e: self._refresh())
        self.summary = ft.Row(spacing=SP_SM, expand=False)
        self.tabs_container = ft.Container()
        self.report_type = "sales"
        self.table = ft.Container(expand=True)
        self.bottom_summary = ft.Container(visible=False)
        self._cached_headers = []
        self._cached_rows = []
        self._cached_summary_lines = []
        self._cached_category = "sales"
        self._cached_base = "report"

    def build(self):
        filters = ft.Row([
            page_title("التقارير (PDF)", "المبيعات = مدفوعة فقط"),
            ft.Container(expand=True), self.date_from, self.date_to,
            ghost_button("آخر 7 أيام", lambda e: self._quick(7), width=120,
                         height=42),
            ghost_button("هذا الشهر", lambda e: self._quick_month(),
                         width=120, height=42),
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=SP_SM)
        self.tabs_container = ft.Container(content=self._build_tabs())
        print_btn = primary_button("معاينة وطباعة", self._export,
                                   icon=ft.icons.PICTURE_AS_PDF, width=180,
                                   height=42)
        self._refresh()
        return ft.Column([
            filters, ft.Container(height=SP_SM), self.summary,
            ft.Container(height=SP_SM),
            ft.Row([self.tabs_container, ft.Container(expand=True),
                    print_btn],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Container(height=SP_SM),
            card(ft.Column([self.table], expand=True, spacing=0),
                 padding=0, hover=False, expand=True),
            ft.Container(height=SP_SM),
            self.bottom_summary,
        ], spacing=0, expand=True)

    def _build_tabs(self):
        tabs = [("sales", "المبيعات"),
                ("purchases", "المشتريات"),
                ("expenses", "المصروفات"),
                ("inventory", "المخزون"),
                ("shipping", "الشحن"),
                ("returns", "المرتجعات"),
                ("profit", "الأرباح")]
        row = ft.Row(spacing=SP_SM, wrap=True)
        for key, label in tabs:
            act = self.report_type == key
            btn = ft.Container(
                content=ft.Text(label,
                                color=BG_BLACK if act else TEXT_PRIMARY,
                                size=FS_SMALL, weight=ft.FontWeight.W_700),
                bgcolor=ACCENT if act else BG_INPUT, border_radius=RADIUS_SM,
                padding=ft.padding.symmetric(horizontal=14, vertical=8),
                on_click=lambda e, k=key: self._switch(k), ink=True)
            if not act:
                btn.on_hover = _hv_ghost
            row.controls.append(btn)
        return row

    def _switch(self, key):
        self.report_type = key
        self.tabs_container.content = self._build_tabs()
        self._refresh()
        try:
            self.tabs_container.update()
        except Exception:
            pass

    def _quick(self, days):
        today = date.today()
        self.date_from.value = (today - timedelta(days=days - 1)).isoformat()
        self.date_to.value = today.isoformat()
        self._refresh()

    def _quick_month(self):
        today = date.today()
        self.date_from.value = today.replace(day=1).isoformat()
        self.date_to.value = today.isoformat()
        self._refresh()

    def _refresh(self, e=None):
        d1 = self.date_from.value or None
        d2 = self.date_to.value or None
        try:
            rep = get_profit_report(d1, d2)
        except Exception:
            rep = {"revenue": 0, "expenses": 0, "net_profit": 0,
                   "total_items": 0, "cogs": 0, "gross_profit": 0,
                   "returns": 0, "net_revenue": 0}
        self.summary.controls = [
            self._stat("مبيعات مدفوعة",
                       money_str(rep["revenue"], self.currency),
                       TEXT_PRIMARY, ft.icons.POINT_OF_SALE),
            self._stat("مرتجعات",
                       money_str(rep.get("returns", 0), self.currency),
                       DANGER, ft.icons.UNDO),
            self._stat("مصروفات",
                       money_str(rep["expenses"], self.currency),
                       WARNING, ft.icons.RECEIPT_LONG),
            self._stat("صافي الربح",
                       money_str(rep["net_profit"], self.currency),
                       SUCCESS if rep["net_profit"] >= 0 else DANGER,
                       ft.icons.SAVINGS),
        ]
        try:
            self.summary.update()
        except Exception:
            pass
        self._load(d1, d2)

    def _load(self, d1, d2):
        self.bottom_summary.visible = False
        self.bottom_summary.content = None
        if self.report_type == "sales":
            self._sales(d1, d2)
        elif self.report_type == "purchases":
            self._purchases(d1, d2)
        elif self.report_type == "expenses":
            self._expenses(d1, d2)
        elif self.report_type == "inventory":
            self._inventory()
        elif self.report_type == "shipping":
            self._shipping(d1, d2)
        elif self.report_type == "returns":
            self._returns(d1, d2)
        elif self.report_type == "profit":
            self._profit(d1, d2)
        try:
            self.bottom_summary.update()
        except Exception:
            pass

    def _summary_chip(self, label, value, color):
        return ft.Container(
            content=ft.Column([
                ft.Text(label, color=TEXT_MUTED, size=FS_TINY,
                        weight=ft.FontWeight.W_700),
                ft.Text(value, color=color, size=18,
                        weight=ft.FontWeight.W_800),
            ], spacing=2, tight=True),
            padding=SP_MD, bgcolor=BG_CARD,
            border=ft.border.all(1, BORDER), border_radius=RADIUS_MD,
            expand=True, height=76)

    def _sales(self, d1, d2):
        invs = [i for i in get_invoices(date_from=d1, date_to=d2)
                if i.get("status") == "paid"]
        total_sales = sum(i["net_total"] for i in invs)
        rep = get_profit_report(d1, d2)
        net_profit = rep["net_profit"]
        self._cached_headers = ["مسلسل", "الفاتورة", "العميل",
                                "التاريخ", "الإجمالي"]
        self._cached_rows = [
            [str(i + 1),
             str(inv.get("invoice_number") or inv["id"]),
             inv.get("customer_name") or "—",
             inv["created_at"][:10],
             f"{inv['net_total']:.2f}"]
            for i, inv in enumerate(invs)]
        self._cached_summary_lines = [
            f"إجمالي المبيعات: {total_sales:.2f} ج.م",
            f"صافي الربح: {net_profit:.2f} ج.م",
        ]
        self._cached_category = "sales"
        self._cached_base = "report_sales"
        rows = [[
            ft.Text(str(inv.get("invoice_number") or inv["id"]),
                    color=TEXT_PRIMARY, size=FS_SMALL,
                    weight=ft.FontWeight.W_700, max_lines=1),
            ft.Text(inv.get("customer_name") or "—", color=TEXT_PRIMARY,
                    size=FS_SMALL, max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS),
            ft.Text(inv["created_at"][:10], color=TEXT_SECONDARY,
                    size=FS_SMALL),
            ft.Text(money_str(inv["net_total"], self.currency),
                    color=TEXT_PRIMARY, size=FS_SMALL,
                    weight=ft.FontWeight.W_700, max_lines=1),
        ] for inv in invs]
        self.table.content = data_table(
            self.page,
            [("الفاتورة", 90), ("العميل", 200), ("التاريخ", 120),
             ("الإجمالي", 120)],
            rows, "لا فواتير مدفوعة.")
        self.bottom_summary.content = ft.Row([
            self._summary_chip("إجمالي المبيعات",
                               money_str(total_sales, self.currency),
                               SUCCESS),
            self._summary_chip("صافي الربح",
                               money_str(net_profit, self.currency),
                               SUCCESS if net_profit >= 0 else DANGER),
        ], spacing=SP_MD)
        self.bottom_summary.visible = True

    def _purchases(self, d1, d2):
        ps = get_purchases_in_range(d1, d2)
        total_purchases = sum(p["total_cost"] for p in ps)
        expected_profit = sum(
            (p["selling_price"] - p["purchase_price"]) * p["quantity"]
            for p in ps)
        self._cached_headers = ["مسلسل", "الكود", "المنتج", "المورد",
                                "الكمية", "الإجمالي"]
        self._cached_rows = [
            [str(i + 1), p["product_code"], p["product_name"],
             p["supplier"] or "—", str(p["quantity"]),
             f"{p['total_cost']:.2f}"]
            for i, p in enumerate(ps)]
        self._cached_summary_lines = [
            f"إجمالي المشتريات: {total_purchases:.2f} ج.م",
            f"الربح المتوقع: {expected_profit:.2f} ج.م",
        ]
        self._cached_category = "purchases"
        self._cached_base = "report_purchases"
        rows = [[
            ft.Text(p["product_code"], color=TEXT_SECONDARY,
                    size=FS_SMALL, max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS),
            ft.Text(p["product_name"], color=TEXT_PRIMARY, size=FS_SMALL,
                    weight=ft.FontWeight.W_600, max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS),
            ft.Text(p["supplier"] or "—", color=TEXT_MUTED, size=FS_SMALL,
                    max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
            ft.Text(str(p["quantity"]), color=TEXT_PRIMARY,
                    size=FS_SMALL),
            ft.Text(money_str(p["total_cost"], self.currency),
                    color=TEXT_PRIMARY, size=FS_SMALL,
                    weight=ft.FontWeight.W_700, max_lines=1),
        ] for p in ps]
        self.table.content = data_table(
            self.page,
            [("الكود", 75), ("المنتج", 150), ("المورد", 110),
             ("الكمية", 65), ("الإجمالي", 110)],
            rows, "لا مشتريات.")
        self.bottom_summary.content = ft.Row([
            self._summary_chip("إجمالي المشتريات",
                               money_str(total_purchases, self.currency),
                               TEXT_PRIMARY),
            self._summary_chip("الربح المتوقع",
                               money_str(expected_profit, self.currency),
                               SUCCESS if expected_profit >= 0 else DANGER),
        ], spacing=SP_MD)
        self.bottom_summary.visible = True

    def _expenses(self, d1, d2):
        es = get_expenses(date_from=d1, date_to=d2)
        total = sum(e["amount"] for e in es)
        self._cached_headers = ["مسلسل", "التاريخ", "الفئة", "المبلغ",
                                "ملاحظات"]
        self._cached_rows = [
            [str(i + 1), e["date"], e["category"], f"{e['amount']:.2f}",
             e["notes"] or "—"]
            for i, e in enumerate(es)]
        self._cached_summary_lines = [
            f"إجمالي المصروفات: {total:.2f} ج.م"]
        self._cached_category = "expenses"
        self._cached_base = "report_expenses"
        rows = [[
            ft.Text(e["date"], color=TEXT_SECONDARY, size=FS_SMALL),
            ft.Text(e["category"], color=TEXT_PRIMARY, size=FS_SMALL,
                    weight=ft.FontWeight.W_600, max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS),
            ft.Text(money_str(e["amount"], self.currency),
                    color=TEXT_PRIMARY, size=FS_SMALL,
                    weight=ft.FontWeight.W_700, max_lines=1),
            ft.Text(e["notes"] or "—", color=TEXT_MUTED, size=FS_SMALL,
                    max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
        ] for e in es]
        self.table.content = data_table(
            self.page,
            [("التاريخ", 100), ("الفئة", 140), ("المبلغ", 100),
             ("ملاحظات", 270)],
            rows, "لا مصروفات.")
        self.bottom_summary.content = ft.Row([
            self._summary_chip("إجمالي المصروفات",
                               money_str(total, self.currency), WARNING),
        ], spacing=SP_MD)
        self.bottom_summary.visible = True

    def _inventory(self):
        products = get_all_products()
        self._cached_headers = ["مسلسل", "الكود", "الاسم", "المورد",
                                "المخزون", "سعر البيع"]
        self._cached_rows = [
            [str(i + 1), p["code"], p["name"],
             p.get("supplier") or "—", str(p["stock_qty"]),
             f"{p['wholesale_price']:.2f}"]
            for i, p in enumerate(products)]
        self._cached_summary_lines = []
        self._cached_category = "inventory"
        self._cached_base = "report_inventory"
        rows = [[
            ft.Text(p["code"], color=TEXT_SECONDARY, size=FS_SMALL,
                    max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
            ft.Text(p["name"], color=TEXT_PRIMARY, size=FS_SMALL,
                    weight=ft.FontWeight.W_600, max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS),
            ft.Text(p.get("supplier") or "—", color=TEXT_MUTED,
                    size=FS_SMALL, max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS),
            ft.Text(str(p["stock_qty"]), color=TEXT_PRIMARY,
                    size=FS_SMALL, weight=ft.FontWeight.W_700),
            ft.Text(money_str(p["wholesale_price"], self.currency),
                    color=TEXT_PRIMARY, size=FS_SMALL, max_lines=1),
        ] for p in products]
        self.table.content = data_table(
            self.page,
            [("الكود", 85), ("الاسم", 170), ("المورد", 130),
             ("المخزون", 75), ("سعر البيع", 95)],
            rows, "لا منتجات.")

    def _shipping(self, d1, d2):
        all_shipped = get_shipped()
        invs = all_shipped
        if d1 or d2:
            filtered = []
            for i in all_shipped:
                cd = (i.get("created_at") or "")[:10]
                if d1 and cd < d1:
                    continue
                if d2 and cd > d2:
                    continue
                filtered.append(i)
            invs = filtered
        self._cached_headers = ["مسلسل", "البوليصة", "الفاتورة",
                                "التاريخ", "العميل", "المحافظة"]
        self._cached_rows = [
            [str(i + 1), inv.get("waybill_number") or "—",
             str(inv.get("invoice_number") or inv["id"]),
             inv["created_at"][:10], inv.get("customer_name") or "—",
             inv.get("customer_governorate") or "—"]
            for i, inv in enumerate(invs)]
        self._cached_summary_lines = []
        self._cached_category = "shipping"
        self._cached_base = "report_shipping"
        rows = [[
            ft.Text(inv.get("waybill_number") or "—", color=SUCCESS,
                    size=FS_SMALL, weight=ft.FontWeight.W_700,
                    max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
            ft.Text(str(inv.get("invoice_number") or inv["id"]),
                    color=TEXT_PRIMARY, size=FS_SMALL,
                    weight=ft.FontWeight.W_600),
            ft.Text(inv["created_at"][:10], color=TEXT_SECONDARY,
                    size=FS_SMALL),
            ft.Text(inv.get("customer_name") or "—", color=TEXT_PRIMARY,
                    size=FS_SMALL, max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS),
            ft.Text(inv.get("customer_governorate") or "—",
                    color=TEXT_SECONDARY, size=FS_SMALL, max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS),
        ] for inv in invs]
        self.table.content = data_table(
            self.page,
            [("البوليصة", 100), ("الفاتورة", 75), ("التاريخ", 100),
             ("العميل", 150), ("المحافظة", 100)],
            rows, "لا شحنات في الفترة المحددة.")

    def _returns(self, d1, d2):
        returns = get_returns(date_from=d1, date_to=d2)
        total_refund = sum(r["total_refund"] for r in returns)
        self._cached_headers = ["مسلسل", "الكود", "الفاتورة",
                                "العميل", "النوع", "التاريخ", "القيمة"]
        self._cached_rows = []
        for i, r in enumerate(returns):
            label = RETURN_REASON_LABELS.get(r["reason_type"],
                                             r["reason_type"])
            self._cached_rows.append([
                str(i + 1),
                r.get("return_code") or str(r["return_number"]),
                str(r["invoice_number"]), r["customer_name"] or "—",
                label, r["created_at"][:10], f"{r['total_refund']:.2f}"])
        self._cached_summary_lines = [
            f"إجمالي المبالغ المرتجعة: {total_refund:.2f} ج.م"]
        self._cached_category = "returns"
        self._cached_base = "report_returns"

        rows = []
        for r in returns:
            label = RETURN_REASON_LABELS.get(r["reason_type"],
                                             r["reason_type"])
            color = DANGER if r["reason_type"] == RETURN_REASON_DEFECT \
                else WARNING
            rows.append([
                ft.Text(r.get("return_code") or str(r["return_number"]),
                        color=SUCCESS, size=FS_SMALL,
                        weight=ft.FontWeight.W_700),
                ft.Text(str(r["invoice_number"]), color=TEXT_SECONDARY,
                        size=FS_SMALL),
                ft.Text(r["customer_name"] or "—", color=TEXT_PRIMARY,
                        size=FS_SMALL, max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS),
                chip(label, color=color),
                ft.Text(r["created_at"][:10], color=TEXT_SECONDARY,
                        size=FS_SMALL),
                ft.Text(money_str(r["total_refund"], self.currency),
                        color=TEXT_PRIMARY, size=FS_SMALL,
                        weight=ft.FontWeight.W_700, max_lines=1),
            ])
        self.table.content = data_table(
            self.page,
            [("الكود", 90), ("الفاتورة", 70), ("العميل", 140),
             ("النوع", 90), ("التاريخ", 90), ("القيمة", 90)],
            rows, "لا مرتجعات في الفترة المحددة.")
        self.bottom_summary.content = ft.Row([
            self._summary_chip("إجمالي المبالغ المرتجعة",
                               money_str(total_refund, self.currency),
                               DANGER),
        ], spacing=SP_MD)
        self.bottom_summary.visible = True

    def _profit(self, d1, d2):
        rep = get_profit_report(d1, d2)
        self._cached_headers = ["البند", "القيمة"]
        self._cached_rows = [
            ["المبيعات", f"{rep['revenue']:.2f} ج.م"],
            ["المرتجعات", f"-{rep['returns']:.2f} ج.م"],
            ["صافي المبيعات", f"{rep['net_revenue']:.2f} ج.م"],
            ["تكلفة المبيعات", f"{rep['cogs']:.2f} ج.م"],
            ["إجمالي الربح", f"{rep['gross_profit']:.2f} ج.م"],
            ["المصروفات", f"{rep['expenses']:.2f} ج.م"],
            ["صافي الربح", f"{rep['net_profit']:.2f} ج.م"],
        ]
        self._cached_summary_lines = []
        self._cached_category = "profits"
        self._cached_base = "report_profit"

        def kv_row(label, value, color):
            return [
                ft.Text(label, color=TEXT_PRIMARY, size=FS_SMALL,
                        weight=ft.FontWeight.W_600),
                ft.Text(value, color=color, size=FS_SMALL,
                        weight=ft.FontWeight.W_800),
            ]

        rows = [
            kv_row("المبيعات",
                   money_str(rep["revenue"], self.currency), SUCCESS),
            kv_row("المرتجعات",
                   f"-{money_str(rep['returns'], self.currency)}", DANGER),
            kv_row("صافي المبيعات",
                   money_str(rep["net_revenue"], self.currency),
                   TEXT_PRIMARY),
            kv_row("تكلفة المبيعات",
                   money_str(rep["cogs"], self.currency), TEXT_SECONDARY),
            kv_row("إجمالي الربح",
                   money_str(rep["gross_profit"], self.currency),
                   SUCCESS if rep["gross_profit"] >= 0 else DANGER),
            kv_row("المصروفات",
                   money_str(rep["expenses"], self.currency), WARNING),
            kv_row("صافي الربح",
                   money_str(rep["net_profit"], self.currency),
                   SUCCESS if rep["net_profit"] >= 0 else DANGER),
        ]
        self.table.content = data_table(
            self.page,
            [("البند", 300), ("القيمة", 220)],
            rows, "لا بيانات.", show_serial=False)

    def _stat(self, label, value, color, icon):
        return ft.Container(
            content=ft.Row([
                ft.Container(content=ft.Icon(icon, size=22, color=color),
                             width=44, height=44, bgcolor=BG_INPUT,
                             border_radius=RADIUS_SM,
                             alignment=ft.alignment.center),
                ft.Container(width=SP_SM),
                ft.Column([
                    ft.Text(label, color=TEXT_MUTED, size=FS_TINY,
                            weight=ft.FontWeight.W_700),
                    ft.Text(value, color=color, size=18,
                            weight=ft.FontWeight.W_800),
                ], spacing=2, tight=True, expand=True),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=SP_MD, bgcolor=BG_CARD,
            border=ft.border.all(1, BORDER), border_radius=RADIUS_MD,
            expand=True, height=80, on_hover=_hv_card)

    def _export(self, e):
        titles = {"sales": "تقرير المبيعات (مدفوعة)",
                  "purchases": "تقرير المشتريات",
                  "expenses": "تقرير المصروفات",
                  "inventory": "تقرير المخزون",
                  "shipping": "تقرير الشحن",
                  "returns": "تقرير المرتجعات",
                  "profit": "تقرير الأرباح"}
        title = titles.get(self.report_type, "تقرير")
        open_report_preview(
            self.page, title,
            self._cached_headers, self._cached_rows,
            self._cached_summary_lines,
            self._cached_category, self._cached_base,
            self.date_from.value or "", self.date_to.value or "")


# --------------------------- SETTINGS ---------------------------
class SettingsView:
    def __init__(self, app, page, user):
        self.app = app; self.page = page; self.user = user
        self.currency = get_currency_symbol()
        self.container = ft.Container(expand=True)
        self._load()

    def _load(self):
        s = get_all_settings()
        self.header_f = text_field("ترويسة الفاتورة",
                                   value=s.get("invoice_header", ""),
                                   multiline=True, width=500)
        self.footer_f = text_field("تذييل الفاتورة",
                                   value=s.get("invoice_footer", ""),
                                   multiline=True, width=500)
        self.currency_f = text_field("رمز العملة",
                                     value=s.get("currency_symbol", "ج.م"),
                                     width=180)
        self.users_container = ft.Container(expand=True)

    def build(self):
        self._hub()
        return self.container

    def _hub(self):
        self.container.content = ft.Column([
            page_title("الإعدادات", "إدارة"),
            ft.Container(height=SP_LG),
            ft.Row([self._tile("إعدادات الفاتورة", "ترويسة وتذييل",
                               ft.icons.RECEIPT_LONG,
                               lambda e: self._invoice_settings()),
                    self._tile("شعار تسجيل الدخول", "صورة مخصصة",
                               ft.icons.IMAGE,
                               lambda e: self._login_logo_settings())],
                   spacing=SP_LG, wrap=True),
            ft.Container(height=SP_LG),
            ft.Row([self._tile("إعدادات الطابعات", "حرارية و A4",
                               ft.icons.PRINT,
                               lambda e: self._printer_settings()),
                    self._tile("إدارة المستخدمين", "إضافة/حذف/تعديل",
                               ft.icons.MANAGE_ACCOUNTS,
                               lambda e: self._users())],
                   spacing=SP_LG, wrap=True),
            ft.Container(height=SP_LG),
            ft.Row([self._tile("نسخ احتياطي", "حفظ .db",
                               ft.icons.BACKUP, lambda e: self._backup()),
                    self._tile("استعادة البيانات", "استرجاع .db",
                               ft.icons.RESTORE, lambda e: self._restore())],
                   spacing=SP_LG, wrap=True),
            ft.Container(height=SP_LG),
            ft.Row([self._tile("مسح البيانات", "حذف كل البيانات (بكلمة سر)",
                               ft.icons.WARNING,
                               lambda e: self._clear_data())],
                   spacing=SP_LG, wrap=True),
        ], spacing=0, expand=True, scroll=ft.ScrollMode.AUTO)
        self._update()

    def _tile(self, title, desc, icon, on_click):
        return ft.Container(
            content=ft.Column([
                ft.Container(content=ft.Icon(icon, size=28,
                                             color=TEXT_PRIMARY),
                             width=56, height=56, bgcolor=BG_INPUT,
                             border_radius=RADIUS_MD,
                             alignment=ft.alignment.center),
                ft.Container(height=SP_SM),
                ft.Text(title, color=TEXT_PRIMARY, size=FS_SECTION,
                        weight=ft.FontWeight.W_800),
                ft.Text(desc, color=TEXT_MUTED, size=FS_SMALL),
                ft.Container(height=SP_SM),
                ft.Row([ft.Text("فتح", color=TEXT_PRIMARY, size=FS_BODY,
                                weight=ft.FontWeight.W_700),
                        ft.Icon(ft.icons.ARROW_FORWARD, size=16,
                                color=TEXT_PRIMARY)], spacing=6),
            ], spacing=0),
            bgcolor=BG_CARD, border=ft.border.all(1, BORDER),
            border_radius=RADIUS_MD, padding=SP_MD, width=300, height=200,
            ink=True, on_click=on_click, on_hover=_hv_card)

    def _clear_data(self):
        pw = text_field("كلمة سر المسؤول *", password=True, width=320,
                        autofocus=True)
        err = ft.Text("", color=DANGER, size=FS_SMALL, visible=False)

        def do_wipe(e):
            err.visible = False
            p = pw.value or ""
            if not p:
                err.value = "أدخل كلمة السر."
                err.visible = True; err.update(); return
            if not verify_admin_password(p):
                err.value = "كلمة السر غير صحيحة."
                err.visible = True; err.update(); return
            self.page.close(dlg)

            def really_do():
                try:
                    clear_all_business_data()
                    snack(self.page, "تم مسح البيانات بنجاح.",
                          kind="success")
                except Exception as ex:
                    snack(self.page, str(ex), kind="error")
            confirm_dialog(
                self.page, "تأكيد نهائي",
                "سيتم حذف جميع البيانات (فواتير، منتجات، عملاء، "
                "مشتريات، مصروفات، مرتجعات). لا يمكن التراجع.",
                really_do, confirm_text="مسح نهائي", danger=True)

        def cancel(e=None):
            self.page.close(dlg)

        dlg = ft.AlertDialog(
            modal=True, bgcolor=BG_CARD,
            title=ft.Text("مسح البيانات",
                          color=TEXT_PRIMARY, weight=ft.FontWeight.W_700,
                          size=FS_SECTION),
            content=ft.Column([
                ft.Text("⚠ هذا الإجراء لا يمكن التراجع عنه.",
                        color=WARNING, size=FS_SMALL,
                        weight=ft.FontWeight.W_600),
                ft.Text("سيتم حذف جميع البيانات التجارية. "
                        "المستخدمون والإعدادات ستبقى.",
                        color=TEXT_SECONDARY, size=FS_SMALL),
                ft.Container(height=SP_SM),
                pw, err,
            ], spacing=SP_SM, width=340),
            actions=[ghost_button("إلغاء", cancel, width=110),
                     primary_button("مسح البيانات", do_wipe,
                                    icon=ft.icons.WARNING, width=170)])
        self.page.open(dlg)

    def _printer_settings(self):
        back = ghost_button("رجوع", lambda e: self._hub(),
                            icon=ft.icons.ARROW_BACK, width=120)

        printers = list_printers()
        if not printers:
            printers = ["(لا توجد طابعات مكتشفة)"]

        current_thermal = get_setting("printer_thermal", "") or ""
        current_a4 = get_setting("printer_a4", "") or ""

        thermal_val = current_thermal if current_thermal in printers else None
        a4_val = current_a4 if current_a4 in printers else None

        thermal_dd = dropdown("الطابعة الحرارية", printers,
                              value=thermal_val, width=420)
        a4_dd = dropdown("طابعة A4", printers, value=a4_val, width=420)

        def save(e):
            try:
                set_settings({
                    "printer_thermal": thermal_dd.value or "",
                    "printer_a4": a4_dd.value or "",
                })
                snack(self.page, "تم حفظ إعدادات الطابعات.", "success")
            except Exception as ex:
                snack(self.page, str(ex), "error")

        def refresh(e):
            self._printer_settings()

        form = card(ft.Column([
            section_title("إعدادات الطباعة"),
            ft.Container(height=SP_SM),
            ft.Text("اختر الطابعات المتصلة بالكمبيوتر:",
                    color=TEXT_MUTED, size=FS_SMALL),
            ft.Container(height=SP_SM),
            thermal_dd,
            ft.Container(height=SP_SM),
            a4_dd,
            ft.Container(height=SP_MD),
            ft.Row([
                primary_button("حفظ", save, icon=ft.icons.SAVE, width=140),
                ghost_button("إعادة تحميل الطابعات", refresh,
                             icon=ft.icons.REFRESH, width=200),
            ], spacing=SP_SM),
            ft.Container(height=SP_SM),
            ft.Text("ملاحظة: يتطلب الطباعة المباشرة إلى طابعة محددة أن "
                    "يكون pywin32 مثبتاً. في حال عدم توفره سيتم استخدام "
                    "الطابعة الافتراضية.", color=TEXT_MUTED,
                    size=FS_TINY),
        ], spacing=SP_SM), padding=SP_MD, hover=False)
        self.container.content = ft.Column([
            ft.Row([back, ft.Container(expand=True)]),
            ft.Container(height=SP_SM),
            page_title("إعدادات الطابعات", ""),
            ft.Container(height=SP_SM), form,
        ], spacing=0, expand=True)
        self._update()

    def _invoice_settings(self):
        back = ghost_button("رجوع", lambda e: self._hub(),
                            icon=ft.icons.ARROW_BACK, width=120)
        save = primary_button("حفظ", self._save_invoice,
                              icon=ft.icons.SAVE, width=140)
        form = card(ft.Column([
            section_title("تخصيص الفاتورة"),
            ft.Container(height=SP_SM),
            self.header_f, self.footer_f,
            ft.Row([self.currency_f], spacing=SP_MD),
            ft.Container(height=SP_MD), save,
        ], spacing=SP_SM), padding=SP_MD, hover=False)
        self.container.content = ft.Column([
            ft.Row([back, ft.Container(expand=True)]),
            ft.Container(height=SP_SM),
            page_title("إعدادات الفاتورة", ""),
            ft.Container(height=SP_SM), form,
        ], spacing=0, expand=True)
        self._update()

    def _save_invoice(self, e=None):
        try:
            set_settings({
                "invoice_header": self.header_f.value or "",
                "invoice_footer": self.footer_f.value or "",
                "currency_symbol": self.currency_f.value or "ج.م",
            })
            snack(self.page, "تم الحفظ.", kind="success")
        except Exception as ex:
            snack(self.page, str(ex), kind="error")

    def _login_logo_settings(self):
        back = ghost_button("رجوع", lambda e: self._hub(),
                            icon=ft.icons.ARROW_BACK, width=120)
        current = get_setting("login_logo_path", "") or ""
        has_logo = bool(current and os.path.exists(current))

        if has_logo:
            preview_content = ft.Image(src=current, width=180, height=180,
                                       fit=ft.ImageFit.CONTAIN)
        else:
            preview_content = ft.Column([
                ft.Icon(ft.icons.IMAGE_NOT_SUPPORTED, size=48,
                        color=TEXT_MUTED),
                ft.Text("لا يوجد شعار مخصص", color=TEXT_MUTED,
                        size=FS_SMALL),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=SP_SM)

        def upload(e):
            def on_result(ev):
                try:
                    p = _extract_path(ev)
                    if not p:
                        return
                    ext = os.path.splitext(p)[1].lower()
                    if ext not in (".png", ".jpg", ".jpeg", ".bmp", ".gif"):
                        snack(self.page, "صيغة غير مدعومة.", kind="error")
                        return
                    dest = os.path.join(BASE_DIR, "login_logo" + ext)
                    shutil.copy2(p, dest)
                    set_settings({"login_logo_path": dest})
                    snack(self.page, "تم تحديث الشعار.", kind="success")
                    self._login_logo_settings()
                except Exception as ex:
                    snack(self.page, str(ex), kind="error")
                finally:
                    _detach_picker(self.page, picker)

            picker = ft.FilePicker(on_result=on_result)
            _attach_picker(self.page, picker)
            try:
                self.page.run_task(self._async_pick_image, picker)
            except Exception as ex:
                snack(self.page, str(ex), kind="error")
                _detach_picker(self.page, picker)

        def remove(e):
            try:
                set_settings({"login_logo_path": ""})
                if current and os.path.exists(current):
                    try:
                        os.remove(current)
                    except Exception:
                        pass
                snack(self.page, "تم إزالة الشعار.", kind="success")
                self._login_logo_settings()
            except Exception as ex:
                snack(self.page, str(ex), kind="error")

        actions = [primary_button("تحميل صورة", upload,
                                  icon=ft.icons.UPLOAD, width=170)]
        if has_logo:
            actions.append(ghost_button("حذف الشعار", remove,
                                        icon=ft.icons.DELETE, width=140,
                                        danger=True))

        self.container.content = ft.Column([
            ft.Row([back, ft.Container(expand=True)]),
            ft.Container(height=SP_SM),
            page_title("شعار تسجيل الدخول", ""),
            ft.Container(height=SP_SM),
            card(ft.Column([
                section_title("معاينة الشعار"),
                ft.Container(height=SP_SM),
                ft.Container(content=preview_content,
                             height=220, bgcolor=BG_INPUT,
                             border_radius=RADIUS_MD,
                             alignment=ft.alignment.center),
                ft.Container(height=SP_SM),
                ft.Row(actions, spacing=SP_SM),
            ], spacing=SP_SM), padding=SP_MD, hover=False),
        ], spacing=0, expand=True)
        self._update()

    async def _async_pick_image(self, picker):
        try:
            await picker.pick_files(
                dialog_title="اختر صورة الشعار",
                allow_multiple=False,
                allowed_extensions=["png", "jpg", "jpeg", "bmp", "gif"])
        except TypeError:
            try:
                picker.pick_files(
                    dialog_title="اختر صورة الشعار",
                    allow_multiple=False,
                    allowed_extensions=["png", "jpg", "jpeg", "bmp", "gif"])
            except Exception as ex:
                snack(self.page, str(ex), kind="error")
                _detach_picker(self.page, picker)
        except Exception as ex:
            snack(self.page, str(ex), kind="error")
            _detach_picker(self.page, picker)

    def _users(self):
        back = ghost_button("رجوع", lambda e: self._hub(),
                            icon=ft.icons.ARROW_BACK, width=120)
        nu = text_field("اسم المستخدم", width=200)
        np_ = text_field("كلمة المرور", password=True, width=200)
        nr = dropdown("الدور", ["admin", "user"], value="user", width=140)

        def do_add(e):
            try:
                create_user(nu.value, np_.value, nr.value)
                nu.value = ""; np_.value = ""; nr.value = "user"
                self._refresh_users()
                snack(self.page, "تم إنشاء المستخدم.", kind="success")
            except Exception as ex:
                snack(self.page, str(ex), kind="error")

        add_form = card(ft.Column([
            section_title("إضافة مستخدم"),
            ft.Container(height=SP_SM),
            ft.Row([nu, np_, nr,
                    primary_button("إضافة", do_add, icon=ft.icons.ADD,
                                   width=110)],
                   spacing=SP_MD,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER,
                   wrap=True),
        ], spacing=0), padding=SP_MD, hover=False)
        self._refresh_users()
        users_card = card(ft.Column([
            section_title("المستخدمون"),
            ft.Container(height=SP_SM),
            ft.Container(content=self.users_container, expand=True),
        ], spacing=0, expand=True), padding=SP_MD, hover=False,
            expand=True)
        self.container.content = ft.Column([
            ft.Row([back, ft.Container(expand=True)]),
            ft.Container(height=SP_SM),
            page_title("إدارة المستخدمين", ""),
            ft.Container(height=SP_SM),
            add_form, ft.Container(height=SP_SM), users_card,
        ], spacing=0, expand=True)
        self._update()

    def _refresh_users(self):
        users = get_all_users()
        rows = []
        for u in users:
            is_self = u["id"] == self.user["id"]
            rows.append([
                ft.Row([ft.Text(u["username"], color=TEXT_PRIMARY,
                                size=FS_SMALL, weight=ft.FontWeight.W_600),
                        chip("أنت") if is_self else ft.Container(width=0)],
                       spacing=6),
                ft.Text(u.get("cashier_code") or "—", color=INFO,
                        size=FS_SMALL, weight=ft.FontWeight.W_700),
                chip("مسؤول" if u["role"] == ROLE_ADMIN else "كاشير",
                     color=(SUCCESS if u["role"] == ROLE_ADMIN
                            else TEXT_SECONDARY)),
                ft.Text(u["created_at"], color=TEXT_MUTED, size=FS_TINY),
            ])

        def row_actions(u):
            is_self = u["id"] == self.user["id"]
            acts = [
                {"label": "تغيير كلمة المرور", "icon": ft.icons.KEY,
                 "handler": lambda u=u: self._pw(u)},
                {"label": "تبديل الدور", "icon": ft.icons.BADGE,
                 "handler": lambda u=u: self._toggle(u)},
            ]
            if not is_self:
                acts.append({"label": "حذف", "icon": ft.icons.DELETE,
                             "handler": lambda u=u: self._del(u),
                             "danger": True})
            return acts

        self.users_container.content = data_table(
            self.page,
            [("اسم المستخدم", 150), ("كود الكاشير", 110),
             ("الدور", 100), ("تاريخ الإنشاء", 140)],
            rows, "لا مستخدمون.", raw_data=users,
            row_actions_builder=row_actions)
        try:
            self.users_container.update()
        except Exception:
            pass

    def _pw(self, u):
        pw = text_field("كلمة المرور الجديدة", password=True, width=300)
        cf = text_field("تأكيد", password=True, width=300)
        err = ft.Text("", color=DANGER, size=FS_SMALL, visible=False)

        def save(e):
            err.visible = False
            if pw.value != cf.value:
                err.value = "غير متطابقة."; err.visible = True
                err.update(); return
            try:
                update_user_password(u["id"], pw.value)
            except Exception as ex:
                err.value = str(ex); err.visible = True; err.update(); return
            self.page.close(dlg)
            snack(self.page, "تم التحديث.", kind="success")

        def cancel(e=None): self.page.close(dlg)

        dlg = ft.AlertDialog(
            modal=True, bgcolor=BG_CARD,
            title=ft.Text(f"كلمة المرور — {u['username']}",
                          color=TEXT_PRIMARY, weight=ft.FontWeight.W_700,
                          size=FS_SECTION),
            content=ft.Column([pw, cf, err], spacing=SP_SM, width=320),
            actions=[ghost_button("إلغاء", cancel, width=110),
                     primary_button("تحديث", save, icon=ft.icons.SAVE,
                                    width=110)])
        self.page.open(dlg)

    def _toggle(self, u):
        new = ROLE_USER if u["role"] == ROLE_ADMIN else ROLE_ADMIN
        try:
            update_user_role(u["id"], new)
            self._refresh_users()
            snack(self.page, f"الدور: {new}", kind="success")
        except Exception as ex:
            snack(self.page, str(ex), kind="error")

    def _del(self, u):
        def do():
            try:
                delete_user(u["id"])
                self._refresh_users()
                snack(self.page, "تم الحذف.", kind="success")
            except Exception as ex:
                snack(self.page, str(ex), kind="error")
        confirm_dialog(self.page, "حذف المستخدم",
                       f"حذف '{u['username']}'؟", do, confirm_text="حذف",
                       danger=True)

    def _backup(self):
        def on_result(e):
            try:
                p = _extract_path(e)
                if not p:
                    return
                if not p.lower().endswith(".db"):
                    p += ".db"
                saved = backup_database(p)
                snack(self.page, f"تم حفظ: {saved}", kind="success")
            except Exception as ex:
                snack(self.page, str(ex), kind="error")
            finally:
                _detach_picker(self.page, picker)

        picker = ft.FilePicker(on_result=on_result)
        _attach_picker(self.page, picker)
        dflt = f"sierra_backup_{datetime.now().strftime('%Y%m%d')}.db"
        try:
            self.page.run_task(self._async_save, picker, dflt)
        except Exception as ex:
            snack(self.page, str(ex), kind="error")
            _detach_picker(self.page, picker)

    async def _async_save(self, picker, dflt):
        try:
            await picker.save_file(dialog_title="حفظ النسخة",
                                   file_name=dflt,
                                   allowed_extensions=["db"])
        except TypeError:
            try:
                picker.save_file(dialog_title="حفظ النسخة", file_name=dflt,
                                 allowed_extensions=["db"])
            except Exception as ex:
                snack(self.page, str(ex), kind="error")
                _detach_picker(self.page, picker)
        except Exception as ex:
            snack(self.page, str(ex), kind="error")
            _detach_picker(self.page, picker)

    def _restore(self):
        def on_result(e):
            try:
                p = _extract_path(e)
                if not p:
                    return

                def do():
                    try:
                        restore_database_from(p)
                    except Exception as ex:
                        snack(self.page, str(ex), kind="error"); return
                    snack(self.page,
                          "تمت الاستعادة. سيتم تسجيل الخروج.",
                          kind="success")
                    try:
                        self.app.logout()
                    except Exception:
                        pass
                confirm_dialog(self.page, "استعادة",
                               f"استبدال البيانات بـ:\n{p}", do,
                               confirm_text="استعادة", danger=True)
            finally:
                _detach_picker(self.page, picker)

        picker = ft.FilePicker(on_result=on_result)
        _attach_picker(self.page, picker)
        try:
            self.page.run_task(self._async_pick, picker)
        except Exception as ex:
            snack(self.page, str(ex), kind="error")
            _detach_picker(self.page, picker)

    async def _async_pick(self, picker):
        try:
            await picker.pick_files(
                dialog_title="اختر ملف النسخة",
                allow_multiple=False, allowed_extensions=["db"])
        except TypeError:
            try:
                picker.pick_files(dialog_title="اختر ملف النسخة",
                                  allow_multiple=False,
                                  allowed_extensions=["db"])
            except Exception as ex:
                snack(self.page, str(ex), kind="error")
                _detach_picker(self.page, picker)
        except Exception as ex:
            snack(self.page, str(ex), kind="error")
            _detach_picker(self.page, picker)

    def _update(self):
        try:
            self.container.update()
        except Exception:
            pass


# ===========================================================================
# MAIN LAYOUT
# ===========================================================================
NAV_ITEMS = [
    ("dashboard", "لوحة التحكم",    ft.icons.DASHBOARD,      False),
    ("pos",       "نقطة البيع",     ft.icons.POINT_OF_SALE,  False),
    ("sales",     "المبيعات",        ft.icons.RECEIPT,        False),
    ("shipping",  "الشحن",           ft.icons.LOCAL_SHIPPING, False),
    ("returns",   "المرتجعات",       ft.icons.UNDO,           False),
    ("customers", "العملاء",         ft.icons.PEOPLE,         False),
    ("loyalty",   "نقاط الولاء",     ft.icons.STAR,           False),
    ("inventory", "المخزون",         ft.icons.INVENTORY_2,    False),
    ("purchases", "المشتريات",       ft.icons.SHOPPING_BAG,   False),
    ("suppliers", "الموردون",        ft.icons.INVENTORY,      False),
    ("expenses",  "المصروفات",       ft.icons.RECEIPT_LONG,   False),
    ("reports",   "التقارير",        ft.icons.BAR_CHART,      True),
    ("settings",  "الإعدادات",       ft.icons.SETTINGS,       True),
]


class MainLayout:
    def __init__(self, app, page, user):
        self.app = app; self.page = page; self.user = user
        self.is_admin = user["role"] == ROLE_ADMIN
        self.content_area = ft.Container(expand=True, padding=SP_LG)
        self.sidebar_col = ft.Column(spacing=4, expand=True,
                                     scroll=ft.ScrollMode.AUTO)
        self.current_key = None

    def build(self):
        sidebar = self._sidebar()
        header = self._header()
        body = ft.Column([header,
                          ft.Container(content=self.content_area,
                                       expand=True, bgcolor=BG_BLACK)],
                         spacing=0, expand=True)
        root = ft.Row([sidebar,
                       ft.Container(content=body, expand=True)],
                      spacing=0, expand=True)
        self._render_sidebar()
        self.navigate("dashboard")
        return root

    def _sidebar(self):
        brand = ft.Container(
            content=ft.Row([
                ft.Container(content=ft.Icon(ft.icons.STOREFRONT, size=18,
                                             color=BG_BLACK),
                             width=36, height=36, bgcolor=ACCENT,
                             border_radius=RADIUS_SM,
                             alignment=ft.alignment.center),
                ft.Column([ft.Text("SIERRA", color=TEXT_PRIMARY, size=16,
                                   weight=ft.FontWeight.W_900),
                           ft.Text("STORE", color=TEXT_MUTED, size=FS_TINY,
                                   weight=ft.FontWeight.W_700)],
                          spacing=0, tight=True)], spacing=SP_SM),
            padding=ft.padding.symmetric(horizontal=SP_MD, vertical=SP_MD))
        return ft.Container(
            content=ft.Column([brand, divider(),
                               ft.Container(content=self.sidebar_col,
                                            padding=SP_SM, expand=True),
                               divider(), self._user_box()],
                              spacing=0, expand=True),
            width=SIDEBAR_WIDTH, bgcolor=BG_SIDEBAR,
            border=ft.border.only(right=ft.BorderSide(1, BORDER)),
            expand=False)

    def _render_sidebar(self):
        self.sidebar_col.controls.clear()
        for key, label, icon, admin_only in NAV_ITEMS:
            if admin_only and not self.is_admin:
                continue
            self.sidebar_col.controls.append(self._nav(key, label, icon))

    def _nav(self, key, label, icon):
        is_active = self.current_key == key

        def _click(e, k=key): self.navigate(k)

        c = ft.Container(
            content=ft.Row([ft.Icon(icon, size=16,
                                    color=(TEXT_PRIMARY if is_active
                                           else TEXT_SECONDARY)),
                            ft.Text(label, size=FS_BODY,
                                    color=(TEXT_PRIMARY if is_active
                                           else TEXT_SECONDARY),
                                    weight=(ft.FontWeight.W_600
                                            if is_active
                                            else ft.FontWeight.W_500))],
                           spacing=SP_SM),
            padding=ft.padding.symmetric(horizontal=SP_MD, vertical=10),
            border_radius=RADIUS_SM,
            bgcolor=BG_CARD if is_active else "transparent",
            on_click=_click, ink=True)
        if not is_active:
            c.on_hover = self._nav_hover(key)
        return c

    def _nav_hover(self, key):
        def handler(e):
            if self.current_key == key:
                return
            act = e.data == "true"
            e.control.bgcolor = (BG_CARD_HOVER if act else "transparent")
            e.control.update()
        return handler

    def _user_box(self):
        role = "مسؤول" if self.is_admin else "كاشير"
        cashier_code = self.user.get("cashier_code") or ""
        subtitle = f"{role}"
        if cashier_code:
            subtitle += f" • {cashier_code}"
        return ft.Container(
            content=ft.Column([
                ft.Row([ft.Container(
                    content=ft.Text(
                        (self.user["username"] or "?")[0].upper(),
                        color=TEXT_PRIMARY, size=FS_SMALL,
                        weight=ft.FontWeight.W_800),
                    width=32, height=32, bgcolor=BG_CARD,
                    border_radius=999, alignment=ft.alignment.center),
                    ft.Column([ft.Text(self.user["username"],
                                       color=TEXT_PRIMARY, size=FS_SMALL,
                                       weight=ft.FontWeight.W_700),
                               ft.Text(subtitle, color=TEXT_MUTED,
                                       size=FS_TINY)],
                              spacing=0, tight=True)], spacing=SP_SM),
                ft.Container(height=SP_SM),
                ft.Container(
                    content=ft.Row([ft.Icon(ft.icons.LOGOUT, size=14,
                                            color=DANGER),
                                    ft.Text("تسجيل الخروج", color=DANGER,
                                            size=FS_SMALL,
                                            weight=ft.FontWeight.W_600)],
                                   spacing=6),
                    padding=ft.padding.symmetric(horizontal=SP_SM,
                                                 vertical=8),
                    border_radius=RADIUS_SM,
                    on_click=lambda e: self.app.logout(), ink=True,
                    on_hover=_hv_danger)],
                spacing=0),
            padding=SP_SM)

    def _header(self):
        now = ft.Text("", color=TEXT_SECONDARY, size=FS_SMALL)

        def tick():
            try:
                now.value = datetime.now().strftime(
                    "%A، %d %B %Y  •  %H:%M:%S")
                now.update()
            except Exception:
                pass

        tick()
        try:
            self.page.run_task(self._clock, now)
        except Exception:
            pass
        return ft.Container(
            content=ft.Row([
                ft.Column([ft.Text("SIERRA STORE", color=TEXT_PRIMARY,
                                   size=20, weight=ft.FontWeight.W_900),
                           ft.Text("سييرا ستور — نظام إدارة متجر الملابس",
                                   color=TEXT_MUTED, size=FS_TINY)],
                          spacing=0, tight=True),
                ft.Container(expand=True),
                ft.Container(content=now,
                             padding=ft.padding.symmetric(horizontal=12,
                                                          vertical=6),
                             bgcolor=BG_CARD,
                             border=ft.border.all(1, BORDER),
                             border_radius=RADIUS_SM)],
                vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.symmetric(horizontal=SP_LG, vertical=12),
            bgcolor=BG_HEADER,
            border=ft.border.only(bottom=ft.BorderSide(1, BORDER)),
            height=HEADER_HEIGHT)

    async def _clock(self, target):
        import asyncio
        while True:
            await asyncio.sleep(1)
            try:
                target.value = datetime.now().strftime(
                    "%A، %d %B %Y  •  %H:%M:%S")
                target.update()
            except Exception:
                return

    def navigate(self, key):
        if key == self.current_key:
            return
        for k, _l, _i, adm in NAV_ITEMS:
            if k == key and adm and not self.is_admin:
                snack(self.page, "لا تملك صلاحية الوصول.", kind="error")
                return
        self.current_key = key
        self._render_sidebar()
        v = self._make_view(key)
        if v is None:
            self.content_area.content = ft.Text("غير موجود",
                                                color=TEXT_MUTED)
        else:
            self.content_area.content = v.build()
        try:
            self.content_area.update()
            self.sidebar_col.update()
        except Exception:
            pass

    def _make_view(self, key):
        if key == "dashboard":
            return DashboardView(self.app, self.page, self.user)
        if key == "pos":
            return POSView(self.app, self.page, self.user)
        if key == "sales":
            return SalesView(self.app, self.page, self.user)
        if key == "shipping":
            return ShippingView(self.app, self.page, self.user)
        if key == "returns":
            return ReturnsView(self.app, self.page, self.user)
        if key == "customers":
            return CustomersView(self.app, self.page, self.user)
        if key == "loyalty":
            return LoyaltyView(self.app, self.page, self.user)
        if key == "inventory":
            return InventoryView(self.app, self.page, self.user)
        if key == "purchases":
            return PurchasesView(self.app, self.page, self.user)
        if key == "suppliers":
            return SuppliersView(self.app, self.page, self.user)
        if key == "expenses":
            return ExpensesView(self.app, self.page, self.user)
        if key == "reports":
            return ReportsView(self.app, self.page, self.user)
        if key == "settings":
            return SettingsView(self.app, self.page, self.user)
        return None


# ===========================================================================
# APPLICATION
# ===========================================================================
class SierraApp:
    def __init__(self, page):
        self.page = page
        self.user = None
        self._setup()
        initialize_database()
        self.show_login()

    def _setup(self):
        self.page.title = "SIERRA STORE"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.bgcolor = BG_BLACK
        self.page.padding = 0
        self.page.spacing = 0
        try:
            self.page.theme = ft.Theme(font_family="Cairo")
        except Exception:
            pass
        try:
            self.page.window.width = 1440
            self.page.window.height = 900
            self.page.window.min_width = 1100
            self.page.window.min_height = 700
        except Exception:
            pass

    def show_login(self):
        self.page.controls.clear()
        self.page.add(LoginView(self, self.page).build())
        self.page.update()

    def on_login_success(self, user):
        self.user = user
        self.show_main()

    def show_main(self):
        if not self.user:
            self.show_login()
            return
        self.page.controls.clear()
        self.page.add(MainLayout(self, self.page, self.user).build())
        self.page.update()

    def logout(self):
        self.user = None
        self.show_login()


def main(page):
    SierraApp(page)


if __name__ == "__main__":
    ft.app(target=main)