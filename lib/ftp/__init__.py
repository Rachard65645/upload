import ftplib
import os

from lib.s3 import uploadFileToS3


def is_ftp_directory(ftp, name):
    """Check if an item is a directory."""
    current = ftp.pwd()
    try:
        ftp.cwd(name)
        ftp.cwd(current)
        return True
    except ftplib.error_perm:
        return False


def download_directory(ftp, remote_dir, local_dir):
    """Download a directory and its contents from an FTP server."""
    if not os.path.exists(local_dir):
        os.makedirs(local_dir)

    ftp.cwd(remote_dir)
    items = ftp.nlst()

    for item in items:
        local_path = os.path.join(local_dir, item)
        remote_path = os.path.join(remote_dir, item)

        if is_ftp_directory(ftp, item):
            download_directory(ftp, item, local_path)
        else:
            # with open(local_path, 'wb') as f:
            #
            #     print(f"[⬇️] Téléchargement de {item}")
            #     ftp.retrbinary(f'RETR {item}', f.write)
            #     print(f"[✅] Téléchargé {item} vers {local_path}")

            s3_file_path = os.path.relpath(local_path)

            uploadFileToS3(
                local_file_path=local_path,
                s3_file_path=s3_file_path
            )


def connect_ftp_and_download(ftp_host, ftp_username, ftp_password, remote_dir, local_dir):
    """Connect to FTP and download the specified directory."""
    ftp = ftplib.FTP(ftp_host)
    ftp.login(ftp_username, ftp_password)
    download_directory(ftp, remote_dir, local_dir)
    ftp.quit()


def downloadFileFromFtp(remote_dir="/", local_dir="./"):
    host = "nl01.upload.cdn13.com"
    username = "1011564.1011564"
    password = "rbhqEaTVvNiqTiIs"

    connect_ftp_and_download(host, username, password, remote_dir, local_dir)
