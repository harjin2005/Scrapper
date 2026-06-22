import paramiko, zipfile, os, io

# ── Re-zip updated code ──────────────────────────────────────────────────────
buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
    base = 'd:/Scrapper'
    skip_dirs = {'__pycache__', '.git', 'downloads', 'checkpoints', 'logs', '.venv', 'node_modules'}
    skip_ext = {'.xlsx', '.xls', '.pem', '.pyc'}
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for f in files:
            fp = os.path.join(root, f)
            ext = os.path.splitext(f)[1].lower()
            if ext in skip_ext:
                continue
            arc = os.path.relpath(fp, base)
            zf.write(fp, arc)

buf.seek(0)
print(f'Zip size: {len(buf.getvalue())/1024:.0f} KB')

# ── Connect ──────────────────────────────────────────────────────────────────
key = paramiko.RSAKey.from_private_key_file('d:/Scrapper/montgomery-scraper.pem')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('3.239.168.243', username='ubuntu', pkey=key, timeout=30)

# Kill any running process
ssh.exec_command('pkill -f montgomery.main 2>/dev/null; sleep 1')

# Upload zip
sftp = ssh.open_sftp()
sftp.putfo(buf, '/home/ubuntu/scraper_new.zip')

# Re-upload fresh token
sftp.put('d:/Scrapper/config/token.json', '/home/ubuntu/scraper/config/token.json')
sftp.close()
print('Uploaded zip + token')

# Extract (overwrite only Python files, keep downloads/config/credentials)
extract_cmd = '''
cd /home/ubuntu
unzip -q -o scraper_new.zip -d scraper_tmp
cp -r scraper_tmp/montgomery/*.py /home/ubuntu/scraper/montgomery/
cp -r scraper_tmp/montgomery/config/config.yaml /home/ubuntu/scraper/montgomery/config/ 2>/dev/null || true
cp -r scraper_tmp/scraper/ /home/ubuntu/scraper/
rm -rf scraper_tmp scraper_new.zip
echo EXTRACT_DONE
'''
stdin, stdout, stderr = ssh.exec_command(f'bash -s', timeout=60)
stdin.write(extract_cmd)
stdin.channel.shutdown_write()
out = stdout.read().decode()
print(out.strip())

# Clear checkpoint so we start from record 1
stdin, stdout, stderr = ssh.exec_command('rm -f /home/ubuntu/scraper/montgomery/checkpoints/*.json && echo checkpoint_cleared')
print(stdout.read().decode().strip())

# Run 10 records on new sheet in background
run_cmd = (
    'cd /home/ubuntu/scraper && '
    'source venv/bin/activate && '
    'nohup python -m montgomery.main '
    '--file montgomery/downloads/Montgomery_Tax_Del_Raw_032726.xlsx '
    '--limit 10 '
    '--sheet "Final  Try " '
    '> /home/ubuntu/run_10.log 2>&1 & echo $!'
)
stdin, stdout, stderr = ssh.exec_command(run_cmd)
pid = stdout.read().decode().strip()
print(f'Started PID: {pid}')
ssh.close()
print('Done — tail /home/ubuntu/run_10.log to monitor')
