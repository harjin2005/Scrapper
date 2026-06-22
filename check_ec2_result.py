import paramiko

key = paramiko.RSAKey.from_private_key_file('d:/Scrapper/montgomery-scraper.pem')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('3.239.168.243', username='ubuntu', pkey=key, timeout=30)

# Full log
stdin, stdout, stderr = ssh.exec_command('cat /home/ubuntu/run_test.log')
log = stdout.read().decode().strip()
lines = log.split('\n')
print(f'Total log lines: {len(lines)}')
print('\n'.join(lines[-40:]))

# Check OOM again
stdin, stdout, stderr = ssh.exec_command('sudo dmesg | grep -i "killed process" | tail -3')
oom = stdout.read().decode().strip()
if oom:
    print('\nOOM:', oom)

# RAM/swap status
stdin, stdout, stderr = ssh.exec_command('free -m')
print('\n' + stdout.read().decode())

ssh.close()
