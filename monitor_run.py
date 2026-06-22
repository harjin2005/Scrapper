import paramiko, time

key = paramiko.RSAKey.from_private_key_file('d:/Scrapper/montgomery-scraper.pem')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('3.239.168.243', username='ubuntu', pkey=key, timeout=30)

# Check if 10-record run started or if we need to check status
stdin, stdout, stderr = ssh.exec_command('pgrep -a python | grep montgomery || echo "no process"')
proc = stdout.read().decode().strip()
print('Process:', proc)

# Check log
stdin, stdout, stderr = ssh.exec_command('wc -l /home/ubuntu/run_10.log 2>/dev/null && tail -20 /home/ubuntu/run_10.log 2>/dev/null || echo "no log yet"')
print(stdout.read().decode())

ssh.close()
