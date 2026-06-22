import paramiko, os

key = paramiko.RSAKey.from_private_key_file('d:/Scrapper/montgomery-scraper.pem')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('3.239.168.243', username='ubuntu', pkey=key, timeout=30)
sftp = ssh.open_sftp()

files = {
    'd:/Scrapper/config/credentials.json': '/home/ubuntu/scraper/montgomery/config/credentials.json',
    'd:/Scrapper/config/token.json': '/home/ubuntu/scraper/montgomery/config/token.json',
}
for local, remote in files.items():
    sftp.put(local, remote)
    print(f'Uploaded: {os.path.basename(local)}')

sftp.close()

# Set headless=true
stdin, stdout, stderr = ssh.exec_command(
    "sed -i 's/headless: false/headless: true/' /home/ubuntu/scraper/montgomery/config/config.yaml"
)
stdout.read()
stdin, stdout, stderr = ssh.exec_command('grep headless /home/ubuntu/scraper/montgomery/config/config.yaml')
print('Config:', stdout.read().decode().strip())

# Make downloads + logs + checkpoints dirs
for d in ['downloads', 'logs', 'checkpoints']:
    ssh.exec_command(f'mkdir -p /home/ubuntu/scraper/montgomery/{d}')

print('Dirs created')
ssh.close()
