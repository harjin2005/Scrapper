import paramiko

key = paramiko.RSAKey.from_private_key_file('d:/Scrapper/montgomery-scraper.pem')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('3.239.168.243', username='ubuntu', pkey=key, timeout=60)

cmds = [
    'sudo fallocate -l 4G /swapfile',
    'sudo chmod 600 /swapfile',
    'sudo mkswap /swapfile',
    'sudo swapon /swapfile',
    "echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab",
    'free -m',
]

for cmd in cmds:
    print(f'>> {cmd}')
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=60)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out: print(out)
    if err and 'tee' not in cmd: print('ERR:', err[:200])

ssh.close()
print('Swap added')
