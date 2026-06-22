import paramiko

key = paramiko.RSAKey.from_private_key_file('d:/Scrapper/montgomery-scraper.pem')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('3.239.168.243', username='ubuntu', pkey=key, timeout=30)

stdin, stdout, stderr = ssh.exec_command('cat /home/ubuntu/run_test.log')
print(stdout.read().decode())
ssh.close()
