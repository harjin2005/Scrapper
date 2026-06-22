import paramiko, time

key = paramiko.RSAKey.from_private_key_file('d:/Scrapper/montgomery-scraper.pem')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('3.239.168.243', username='ubuntu', pkey=key, timeout=30)

# Upload the Excel file first (78MB - takes a moment)
print('Uploading Excel file...')
sftp = ssh.open_sftp()
sftp.put(
    'd:/Scrapper/montgomery/downloads/Montgomery_Tax_Del_Raw_032726.xlsx',
    '/home/ubuntu/scraper/montgomery/downloads/Montgomery_Tax_Del_Raw_032726.xlsx',
    callback=lambda x, y: print(f'\r  {x/1024/1024:.1f}/{y/1024/1024:.1f} MB', end='', flush=True)
)
sftp.close()
print('\nExcel uploaded')

# Run 1-record test
print('\nRunning 1-record test...')
cmd = (
    'cd /home/ubuntu/scraper && '
    'source venv/bin/activate && '
    'python -m montgomery.main '
    '--file montgomery/downloads/Montgomery_Tax_Del_Raw_032726.xlsx '
    '--limit 1 2>&1'
)
stdin, stdout, stderr = ssh.exec_command(cmd, timeout=600)
for line in stdout:
    print(line.rstrip())

ssh.close()
