"""deploy/pull-backup.sh: the off-site backup pull that runs on a Mac. NEVER connects to a server: every test runs the script against a local stand-in
for ssh (PULL_BACKUP_SSH, or a stub `ssh` first on PATH) and a stub `sudo`, with a temporary folder playing the server's backups folder."""
import gzip
import hashlib
import os
import plistlib
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, 'deploy', 'pull-backup.sh')
PLIST = os.path.join(ROOT, 'deploy', 'com.fichaunica.pull-backup.plist.example')
BASH = '/bin/bash'   # macOS ships bash 3.2: that is the one the script must run on

FAKE_SSH = """#!/bin/sh
# stands in for: ssh <alias> '<remote command>'. Records what it was asked to run, then runs it HERE.
printf '%s\\n' "$*" >> "$PULL_BACKUP_FAKE_LOG"
[ -n "${FAKE_SSH_FAIL:-}" ] && { echo "$FAKE_SSH_FAIL" >&2; exit 255; }
for last; do :; done
exec /bin/sh -c "$last"
"""
FAKE_SUDO = """#!/bin/sh
# stands in for sudo: -n (never ask) is accepted, then the command runs as is.
[ "$1" = "-n" ] || { echo "sudo called without -n" >&2; exit 1; }
shift
exec "$@"
"""


def gz(payload=b'una base de datos de prueba' * 50):
    import io
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode='wb', mtime=0) as f:
        f.write(payload)
    return buf.getvalue()


def name(day, hhmmss='091500'):
    return 'llave-202611%02d-%s.db.gz' % (day, hhmmss)


def tree_hash(d):
    """Everything in a folder: names, sizes, contents."""
    h = hashlib.sha256()
    for n in sorted(os.listdir(d)):
        p = os.path.join(d, n)
        h.update(n.encode())
        if os.path.isfile(p):
            with open(p, 'rb') as f:
                h.update(f.read())
    return h.hexdigest()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.server = os.path.join(self.tmp, 'server-backups')        # plays /srv/fichaunica-data/backups
        self.dest = os.path.join(self.tmp, 'mi carpeta', 'copias')   # a space on purpose
        self.bin = os.path.join(self.tmp, 'bin')
        for d in (self.server, self.bin):
            os.makedirs(d)
        self.fake_log = os.path.join(self.tmp, 'ssh-calls.log')
        open(self.fake_log, 'w').close()
        for n, body in (('fake-ssh', FAKE_SSH), ('sudo', FAKE_SUDO)):
            with open(os.path.join(self.bin, n), 'w') as f:
                f.write(body)
            os.chmod(os.path.join(self.bin, n), 0o755)

    def put(self, fname, data=None, where=None):
        with open(os.path.join(where or self.server, fname), 'wb') as f:
            f.write(gz() if data is None else data)

    def run_script(self, *args, **env_extra):
        env = {'PATH': self.bin + ':/usr/bin:/bin', 'HOME': self.tmp, 'PULL_BACKUP_SSH': os.path.join(self.bin, 'fake-ssh'),
               'PULL_BACKUP_REMOTE_DIR': self.server, 'PULL_BACKUP_FAKE_LOG': self.fake_log}
        env.update(env_extra)
        return subprocess.run([BASH, SCRIPT] + list(args), capture_output=True, text=True, env=env, timeout=60)

    def calls(self):
        with open(self.fake_log) as f:
            return [x for x in f.read().split('\n') if x]

    def log_lines(self):
        p = os.path.join(self.dest, 'pull-backup.log')
        if not os.path.isfile(p):
            return []
        with open(p) as f:
            return [x for x in f.read().split('\n') if x]

    def dest_files(self):
        return sorted(os.listdir(self.dest))


class Pull(Base):
    def test_copies_only_the_newest_and_verifies_it(self):
        for d in (1, 2, 3):
            self.put(name(d), gz(b'dia %d' % d * 100))
            self.put(name(d) + '.sha256', b'abc  x\n')
        self.put('media-20261103.tar.gz', b'no es la base')
        self.put(name(4) + '.part', b'a medio escribir')
        before = tree_hash(self.server)
        r = self.run_script(self.dest)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.dest_files(), [name(3), 'pull-backup.log'])           # the newest by NAME, not the sidecar, the media archive or the .part
        with open(os.path.join(self.dest, name(3)), 'rb') as f:
            self.assertEqual(gzip.decompress(f.read()), b'dia 3' * 100)
        self.assertEqual(oct(os.stat(os.path.join(self.dest, name(3))).st_mode & 0o777), '0o600')   # client data: owner only
        lines = self.log_lines()
        self.assertEqual(len(lines), 1)
        self.assertRegex(lines[0], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d{4} OK %s \d+ bytes; copias en la carpeta: 1; borradas aquí: 0$' % re.escape(name(3)))
        self.assertEqual(r.stdout.strip(), lines[0])
        self.assertEqual(tree_hash(self.server), before)                              # nothing changed on the "server"

    def test_the_newest_is_picked_by_name_not_by_file_date(self):
        self.put(name(9)), self.put(name(2))
        os.utime(os.path.join(self.server, name(2)), (4102444800, 4102444800))        # the OLD one has the newest date
        self.assertEqual(self.run_script(self.dest).returncode, 0)
        self.assertEqual(self.dest_files(), [name(9), 'pull-backup.log'])

    def test_only_two_kinds_of_remote_command_and_nothing_that_deletes(self):
        self.put(name(1)), self.put(name(2))
        self.run_script(self.dest)
        calls = self.calls()
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], "sudo -n ls -1 %s" % self.server)
        self.assertEqual(calls[1], "sudo -n cat %s/%s" % (self.server, name(2)))
        for c in calls:
            self.assertNotRegex(c, r'\b(rm|mv|cp|truncate|dd|tee|chmod|chown|ln|rsync|scp|sed -i|>)\b|>')

    def test_a_second_run_does_not_download_again(self):
        self.put(name(5))
        self.assertEqual(self.run_script(self.dest).returncode, 0)
        before = len(self.calls())
        r = self.run_script(self.dest)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.calls()) - before, 1)                               # only the listing; no cat
        lines = self.log_lines()
        self.assertEqual(len(lines), 2)
        self.assertRegex(lines[1], r' YA ESTABA %s \d+ bytes' % re.escape(name(5)))

    def test_a_damaged_local_copy_is_fetched_again(self):
        self.put(name(5))
        os.makedirs(self.dest)
        self.put(name(5), b'esto no es gzip', where=self.dest)
        r = self.run_script(self.dest)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.dest, name(5)), 'rb') as f:
            self.assertEqual(gzip.decompress(f.read()), gzip.decompress(gz()))
        self.assertRegex(self.log_lines()[-1], r' OK ')

    def test_keeps_the_newest_14_here_and_leaves_everything_else_alone(self):
        os.makedirs(self.dest)
        for d in range(1, 17):                                                        # 16 older copies already here (days 1..16 of October)
            self.put('llave-202610%02d-091500.db.gz' % d, where=self.dest)
        self.put('notas.txt', b'mis notas', where=self.dest)
        self.put('llave-20261016-091500.db.gz.sha256', b'x', where=self.dest)
        self.put(name(3))
        r = self.run_script(self.dest)
        self.assertEqual(r.returncode, 0, r.stderr)
        dbs = [f for f in self.dest_files() if f.endswith('.db.gz')]
        self.assertEqual(len(dbs), 14)
        self.assertEqual(dbs[-1], name(3))                                            # the new one is the newest and is kept
        self.assertEqual(dbs[0], 'llave-20261004-091500.db.gz')                      # 16 old + the new one = 17: the 3 oldest (Oct 1..3) went
        self.assertIn('notas.txt', self.dest_files())
        self.assertIn('llave-20261016-091500.db.gz.sha256', self.dest_files())        # not a .db.gz: not touched
        self.assertIn('pull-backup.log', self.dest_files())
        self.assertRegex(self.log_lines()[-1], r'copias en la carpeta: 14; borradas aquí: 3$')
        self.assertEqual(len(os.listdir(self.server)), 1)                             # the server folder was never touched

    def test_keep_can_be_changed_and_never_drops_the_new_copy(self):
        os.makedirs(self.dest)
        for d in range(20, 30):                                                       # copies named NEWER than the server's, e.g. a wrong clock
            self.put('llave-202612%02d-091500.db.gz' % d, where=self.dest)
        self.put(name(3))
        self.assertEqual(self.run_script(self.dest, PULL_BACKUP_KEEP='3').returncode, 0)
        self.assertIn(name(3), self.dest_files())


class Failures(Base):
    def assert_failed(self, r, why):
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        lines = self.log_lines()
        self.assertEqual(len(lines), 1)
        self.assertRegex(lines[0], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d{4} ERROR ')
        self.assertIn(why, lines[0])
        self.assertEqual(r.stdout, '')
        self.assertIn('ERROR', r.stderr)
        self.assertEqual([f for f in self.dest_files() if f.startswith('.')], [])     # no temp file left behind

    def test_ssh_down_keeps_what_you_have_and_prunes_nothing(self):
        os.makedirs(self.dest)
        for d in range(1, 17):
            self.put('llave-202610%02d-091500.db.gz' % d, where=self.dest)
        r = self.run_script(self.dest, FAKE_SSH_FAIL='ssh: connect to host fichaunica-vps port 22: Operation timed out')
        self.assertEqual(r.returncode, 1)
        lines = self.log_lines()
        self.assertEqual(len(lines), 1)
        self.assertIn('no pude leer la carpeta de respaldos del servidor', lines[0])
        self.assertIn('Operation timed out', lines[0])
        self.assertEqual(self.dest_files(), sorted(['pull-backup.log'] + ['llave-202610%02d-091500.db.gz' % d for d in range(1, 17)]))   # pruning waits for a good pull

    def test_the_server_has_no_copy(self):
        self.put('media-20261103.tar.gz', b'x')
        r = self.run_script(self.dest)
        self.assert_failed(r, 'no tiene ninguna copia')

    def test_a_damaged_download_is_not_kept(self):
        self.put(name(1))
        self.put(name(2), gz()[:-9])                                                  # cut short
        r = self.run_script(self.dest)
        self.assert_failed(r, 'gzip -t dice que está dañada o incompleta')
        self.assertEqual(self.dest_files(), ['pull-backup.log'])

    def test_a_download_that_is_not_gzip_at_all_is_not_kept(self):
        self.put(name(2), b'<html>error</html>')
        self.assert_failed(self.run_script(self.dest), 'gzip -t')
        self.assertNotIn(name(2), self.dest_files())

    def test_an_empty_download_is_not_kept(self):
        self.put(name(2), b'')
        self.assert_failed(self.run_script(self.dest), 'llegó vacía')
        self.assertEqual(self.dest_files(), ['pull-backup.log'])

    def test_a_failed_pull_leaves_older_good_copies_untouched(self):
        os.makedirs(self.dest)
        self.put(name(1), where=self.dest)
        good = tree_hash(self.dest)
        self.put(name(2), b'roto')
        r = self.run_script(self.dest)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.dest_files(), [name(1), 'pull-backup.log'])
        with open(os.path.join(self.dest, name(1)), 'rb') as f:
            self.assertEqual(gzip.decompress(f.read()), gzip.decompress(gz()))
        self.assertNotEqual(tree_hash(self.dest), good)                               # only the log grew

    def test_sudo_without_a_password_is_required(self):
        """The script must ask sudo for -n (never prompt): the stub sudo refuses a call without it."""
        self.put(name(1))
        self.assertEqual(self.run_script(self.dest).returncode, 0)


class Usage(Base):
    def test_no_argument(self):
        r = self.run_script()
        self.assertEqual(r.returncode, 2)
        self.assertIn('Uso:', r.stderr)
        self.assertEqual(self.calls(), [])

    def test_too_many_arguments_and_empty_argument(self):
        self.assertEqual(self.run_script(self.dest, 'otra').returncode, 2)
        self.assertEqual(self.run_script('').returncode, 2)
        self.assertEqual(self.calls(), [])

    def test_destination_that_is_a_file(self):
        p = os.path.join(self.tmp, 'archivo')
        open(p, 'w').close()
        r = self.run_script(p)
        self.assertEqual(r.returncode, 2)
        self.assertIn('No es una carpeta', r.stderr)

    def test_bad_settings(self):
        self.assertEqual(self.run_script(self.dest, PULL_BACKUP_KEEP='0').returncode, 2)
        self.assertEqual(self.run_script(self.dest, PULL_BACKUP_KEEP='x').returncode, 2)
        self.assertEqual(self.run_script(self.dest, PULL_BACKUP_REMOTE_DIR='/srv/a; rm -rf /').returncode, 2)
        self.assertEqual(self.calls(), [])


class DefaultSsh(Base):
    """Without the override the script runs `ssh ... fichaunica-vps '<command>'`. A stub `ssh` first on PATH records that and runs the command
    here, so nothing leaves this machine."""

    def test_uses_the_fichaunica_vps_alias_and_never_prompts(self):
        stub = os.path.join(self.bin, 'ssh')
        os.rename(os.path.join(self.bin, 'fake-ssh'), stub)
        env = {'PATH': self.bin + ':/usr/bin:/bin'}
        found = subprocess.run(['/bin/sh', '-c', 'command -v ssh'], capture_output=True, text=True, env=env).stdout.strip()
        self.assertEqual(found, stub)                                                 # the stub is what the script will find: no real ssh runs
        self.put(name(7))
        r = subprocess.run([BASH, SCRIPT, self.dest], capture_output=True, text=True, timeout=60,
                           env=dict(env, HOME=self.tmp, PULL_BACKUP_REMOTE_DIR=self.server, PULL_BACKUP_FAKE_LOG=self.fake_log))
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = self.calls()
        self.assertEqual(len(calls), 2)
        for c in calls:
            self.assertRegex(c, r'^-o BatchMode=yes -o ConnectTimeout=\d+ .*fichaunica-vps sudo -n ')
        self.assertEqual(self.dest_files(), [name(7), 'pull-backup.log'])


class Portability(unittest.TestCase):
    def read(self, p):
        with open(p, encoding='utf-8') as f:
            return f.read()

    def test_script_is_bash_3_2_clean_and_executable(self):
        src = self.read(SCRIPT)
        self.assertTrue(src.startswith('#!/bin/bash\n'))
        self.assertTrue(os.access(SCRIPT, os.X_OK))
        for bad in (r'\bmapfile\b', r'\breadarray\b', r'declare\s+-A', r'\$\{[^}]*,,[^}]*\}', r'\$\{[^}]*\^\^[^}]*\}', r'&>>', r'\|&', r'\bcoproc\b', r'\[\[.*=~',
                    r'\bstat\s+-c\b', r'\bsed\s+-i\b', r'\bgrep\s+-P\b', r'\breadlink\s+-f\b', r'\bdate\s+-d\b', r'\bwait\s+-n\b', r'\bglobstar\b'):
            self.assertNotRegex(src, bad)
        r = subprocess.run([BASH, '-n', SCRIPT], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stderr), (0, ''))
        if sys.platform == 'darwin':
            v = subprocess.run([BASH, '--version'], capture_output=True, text=True).stdout
            self.assertIn('version 3.2', v)                                           # the tests above really ran on the Mac's own bash

    def test_script_never_deletes_on_the_server(self):
        src = self.read(SCRIPT)
        remote = re.findall(r'\$SSH_CMD "([^"]*)"', src)
        self.assertEqual(remote, ['sudo -n ls -1 $REMOTE_DIR', 'sudo -n cat $REMOTE_DIR/$NEWEST'])
        self.assertEqual(src.count('rm -f'), 3)                                       # temp file, error file, old local copies: all local
        self.assertNotRegex(src, r'rm\s+-[a-zA-Z]*r')

    def test_plist_example_is_a_valid_5am_launchd_job_with_placeholder_paths(self):
        with open(PLIST, 'rb') as f:
            d = plistlib.load(f)
        self.assertEqual(d['Label'], 'com.fichaunica.pull-backup')
        self.assertEqual(d['StartCalendarInterval'], {'Hour': 5, 'Minute': 0})
        self.assertEqual(d['ProgramArguments'][0], '/bin/bash')
        self.assertTrue(d['ProgramArguments'][1].endswith('deploy/pull-backup.sh'))
        self.assertFalse(d['RunAtLoad'])
        txt = self.read(PLIST)
        for p in re.findall(r'/Users/[^/<\s]+', txt):
            self.assertEqual(p, '/Users/CHANGE_ME')
        self.assertIn('launchctl bootstrap', txt)
        self.assertIn('launchctl bootout', txt)
        self.assertIn('plutil -lint', txt)
        self.assertEqual(os.path.basename(PLIST), 'com.fichaunica.pull-backup.plist.example')


if __name__ == '__main__':
    unittest.main()
