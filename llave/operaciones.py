"""Operaciones: a small deal tracker for agents (interesado -> cerrada). Every query is scoped by agency_id:
one agency can never read or change another's deals. Tasks are pre-loaded from the cierre checklist (venta) or a renta list."""
from . import formatos

STAGES = [('interesado', 'Interesado'), ('visita', 'Visita'), ('oferta', 'Oferta'), ('apartado', 'Apartado'),
          ('firma', 'Firma'), ('cerrada', 'Cerrada'), ('perdida', 'Perdida')]
STAGE_LABEL = dict(STAGES)
KINDS = ('venta', 'renta')
RENTA_TASKS = ['Identificación del inquilino', 'Comprobante de ingresos', 'Aval o póliza jurídica',
               'Contrato firmado', 'Depósito recibido', 'Entrega con inventario']


def default_tasks(kind):
    if kind == 'renta':
        return list(RENTA_TASKS)
    return [l[2:].strip() for l in formatos.BY_KEY['cierre']['body'] if l.startswith('☐ ')]


def create(con, agency_id, client_name, kind, client_phone='', listing_id=None, amount_cents=None, notes=''):
    client_name = (client_name or '').strip()
    if not client_name:
        raise ValueError('Pon el nombre del cliente.')
    if kind not in KINDS:
        raise ValueError('Elige venta o renta.')
    if listing_id and not con.execute('SELECT 1 FROM listings WHERE id=? AND agency_id=?', (listing_id, agency_id)).fetchone():
        raise ValueError('Esa propiedad no es tuya.')
    cur = con.execute('INSERT INTO deals(agency_id, listing_id, client_name, client_phone, kind, amount_cents, notes) VALUES (?,?,?,?,?,?,?)',
                      (agency_id, listing_id or None, client_name[:120], (client_phone or '').strip()[:40], kind, amount_cents, (notes or '').strip()[:2000]))
    did = cur.lastrowid
    for i, label in enumerate(default_tasks(kind)):
        con.execute('INSERT INTO deal_tasks(deal_id, label, position) VALUES (?,?,?)', (did, label, i))
    con.commit()
    return did


def get(con, agency_id, deal_id):
    return con.execute('SELECT d.*, l.title AS listing_title, l.ref AS listing_ref FROM deals d LEFT JOIN listings l ON l.id=d.listing_id '
                       'WHERE d.id=? AND d.agency_id=?', (deal_id, agency_id)).fetchone()


def tasks(con, agency_id, deal_id):
    return con.execute('SELECT t.* FROM deal_tasks t JOIN deals d ON d.id=t.deal_id WHERE t.deal_id=? AND d.agency_id=? ORDER BY t.position, t.id',
                       (deal_id, agency_id)).fetchall()


def listing_all(con, agency_id, stage=''):
    sql = ('SELECT d.*, (SELECT COUNT(*) FROM deal_tasks t WHERE t.deal_id=d.id) AS n_tasks, '
           '(SELECT COUNT(*) FROM deal_tasks t WHERE t.deal_id=d.id AND t.done=1) AS n_done FROM deals d WHERE d.agency_id=?')
    args = [agency_id]
    if stage in STAGE_LABEL:
        sql += ' AND d.stage=?'
        args.append(stage)
    return con.execute(sql + ' ORDER BY d.updated_at DESC, d.id DESC', args).fetchall()


def counts(con, agency_id):
    out = {k: 0 for k, _l in STAGES}
    for r in con.execute('SELECT stage, COUNT(*) n FROM deals WHERE agency_id=? GROUP BY stage', (agency_id,)):
        out[r['stage']] = r['n']
    return out


def set_stage(con, agency_id, deal_id, stage):
    if stage not in STAGE_LABEL:
        raise ValueError('Etapa no válida.')
    cur = con.execute("UPDATE deals SET stage=?, updated_at=datetime('now') WHERE id=? AND agency_id=?", (stage, deal_id, agency_id))
    con.commit()
    return cur.rowcount == 1


def set_notes(con, agency_id, deal_id, notes):
    cur = con.execute("UPDATE deals SET notes=?, updated_at=datetime('now') WHERE id=? AND agency_id=?",
                      ((notes or '').strip()[:2000], deal_id, agency_id))
    con.commit()
    return cur.rowcount == 1


def set_task(con, agency_id, deal_id, task_id, done):
    cur = con.execute('UPDATE deal_tasks SET done=? WHERE id=? AND deal_id=? AND deal_id IN (SELECT id FROM deals WHERE id=? AND agency_id=?)',
                      (1 if done else 0, task_id, deal_id, deal_id, agency_id))
    con.commit()
    return cur.rowcount == 1


def add_task(con, agency_id, deal_id, label):
    label = (label or '').strip()[:160]
    if not label:
        raise ValueError('Escribe la tarea.')
    if not con.execute('SELECT 1 FROM deals WHERE id=? AND agency_id=?', (deal_id, agency_id)).fetchone():
        return False
    pos = con.execute('SELECT COALESCE(MAX(position)+1, 0) FROM deal_tasks WHERE deal_id=?', (deal_id,)).fetchone()[0]
    con.execute('INSERT INTO deal_tasks(deal_id, label, position) VALUES (?,?,?)', (deal_id, label, pos))
    con.commit()
    return True
