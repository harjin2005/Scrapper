import paramiko, time

key = paramiko.RSAKey.from_private_key_file('d:/Scrapper/montgomery-scraper.pem')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('3.239.168.243', username='ubuntu', pkey=key, timeout=30)

# Run in background with nohup, pipe all output to log file
cmd = (
    'cd /home/ubuntu/scraper && '
    'source venv/bin/activate && '
    'nohup python -m montgomery.main '
    '--file montgomery/downloads/Montgomery_Tax_Del_Raw_032726.xlsx '
    '--limit 1 > /home/ubuntu/run_test.log 2>&1 &'
    ' echo $!'
)
stdin, stdout, stderr = ssh.exec_command(cmd)
pid = stdout.read().decode().strip()
print(f'Started PID: {pid}')

# Poll every 30s until done
for attempt in range(30):
    time.sleep(30)
    stdin, stdout, stderr = ssh.exec_command(f'kill -0 {pid} 2>/dev/null && echo running || echo done')
    status = stdout.read().decode().strip()

    # Show last few log lines
    stdin, stdout, stderr = ssh.exec_command('tail -5 /home/ubuntu/run_test.log 2>/dev/null')
    tail = stdout.read().decode().strip()
    print(f'[{attempt+1}] Status: {status}')
    if tail:
        print(f'  Last log: {tail}')

    if status == 'done':
        print('\n=== FINAL LOG ===')
        stdin, stdout, stderr = ssh.exec_command('tail -30 /home/ubuntu/run_test.log')
        print(stdout.read().decode())
        break

ssh.close()
