import paramiko, time

key = paramiko.RSAKey.from_private_key_file('d:/Scrapper/montgomery-scraper.pem')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('3.239.168.243', username='ubuntu', pkey=key, timeout=30)

# Check if run is still going or finished
stdin, stdout, stderr = ssh.exec_command(
    'ls -la /home/ubuntu/scraper/montgomery/logs/ 2>/dev/null && '
    'cat /home/ubuntu/scraper/montgomery/logs/run_report_2026-05-26.json 2>/dev/null || echo "No report yet"'
)
print(stdout.read().decode())

# Also check if process is running
stdin, stdout, stderr = ssh.exec_command('pgrep -a python | grep montgomery || echo "No montgomery process running"')
print("Process:", stdout.read().decode().strip())

ssh.close()
