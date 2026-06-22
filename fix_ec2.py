import paramiko

key = paramiko.RSAKey.from_private_key_file('d:/Scrapper/montgomery-scraper.pem')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('3.239.168.243', username='ubuntu', pkey=key, timeout=30)

# Kill any running python processes
stdin, stdout, stderr = ssh.exec_command('pkill -f montgomery.main; sleep 2; echo killed')
print(stdout.read().decode().strip())

# Check current token
stdin, stdout, stderr = ssh.exec_command('cat /home/ubuntu/scraper/montgomery/config/token.json | python3 -c "import sys,json; t=json.load(sys.stdin); print(\'expiry:\',t.get(\'expiry\',\'none\')); print(\'has_refresh:\',bool(t.get(\'refresh_token\')))"')
print('Token info:', stdout.read().decode().strip())

ssh.close()
