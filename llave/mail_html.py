"""The look of every email Ficha Única sends to an agent: simple tables, inline styles only (mail apps ignore <style> and fonts),
colours from the Lotería design system (config/design-system/MASTER.md in the lane). No logo image and nothing hotlinked:
the brand is the text wordmark with a chile "ficha" dot. Text on chile / nopal / cempasúchil is always tinta, never white."""
from html import escape

INK, PAPER, WHITE, CHILE, CEMPA, NOPAL, SOFT = '#1B1236', '#FFF9EE', '#FFFFFF', '#FF4F1F', '#FFB800', '#0FB56D', '#5E5478'
FONT = "system-ui,-apple-system,'Segoe UI',Roboto,Arial,sans-serif"
SERIF = "'Cooper Black',Georgia,serif"
BRAND = 'Ficha Única'


def esc(x):
    return escape('' if x is None else str(x), quote=True)


def button(href, label, color=NOPAL):
    """One big tap target. `color` is the fill; the label is tinta on top of it."""
    return ('<table role="presentation" width="100%%" cellpadding="0" cellspacing="0" style="margin:18px 0 6px 0"><tr>'
            '<td align="center" bgcolor="%s" style="background:%s;border:3px solid %s;border-radius:12px">'
            '<a href="%s" style="display:block;padding:18px 16px;font-family:%s;font-size:20px;font-weight:800;line-height:1.2;'
            'color:%s;text-decoration:none">%s</a></td></tr></table>') % (color, color, INK, esc(href), FONT, INK, esc(label))


def text_link(href, label):
    return '<a href="%s" style="color:%s;font-weight:700">%s</a>' % (esc(href), INK, esc(label))


def para(inner_html, size=17, color=INK, bold=False, top=0, bottom=10):
    return '<p style="margin:%dpx 0 %dpx 0;font-family:%s;font-size:%dpx;line-height:1.4;color:%s;font-weight:%s">%s</p>' % (
        top, bottom, FONT, size, color, '800' if bold else '400', inner_html)


def shell(title, inner, footer=''):
    """Full HTML document around `inner` (already escaped HTML)."""
    return ('<!doctype html><html lang="es-MX"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="color-scheme" content="light"><title>%s</title></head>'
            '<body style="margin:0;padding:0;background:%s">'
            '<table role="presentation" width="100%%" cellpadding="0" cellspacing="0" bgcolor="%s" style="background:%s"><tr><td align="center" style="padding:16px 12px">'
            '<table role="presentation" width="100%%" cellpadding="0" cellspacing="0" style="max-width:560px">'
            '<tr><td style="padding:0 0 12px 2px;font-family:%s;font-size:26px;line-height:1.1;color:%s">'
            '<span style="display:inline-block;width:14px;height:14px;border-radius:7px;background:%s;border:2px solid %s;vertical-align:middle;margin-right:8px"></span>%s</td></tr>'
            '<tr><td style="background:%s;border:3px solid %s;border-radius:12px;padding:22px 20px">%s</td></tr>'
            '<tr><td style="padding:12px 4px 0 4px;font-family:%s;font-size:13px;line-height:1.4;color:%s">%s</td></tr>'
            '</table></td></tr></table></body></html>') % (
        esc(title), PAPER, PAPER, PAPER, SERIF, INK, CHILE, INK, esc(BRAND), WHITE, INK, inner, FONT, SOFT,
        footer or 'Ficha Única, un servicio de Ciao Bella Marketing.')
