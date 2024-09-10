import boto3
import os
from botocore.exceptions import NoCredentialsError, ClientError
from boto3.s3.transfer import TransferConfig, S3Transfer
from tqdm import tqdm


def list_s3_directories(bucket_name, access_key, secret_key, endpoint_url):
    try:
        print("Création du client S3...")
        s3 = boto3.resource(
            's3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            endpoint_url=endpoint_url
        )
        print("Client S3 créé avec succès.")

        print(f"Listing des dossiers dans le bucket {bucket_name}...")
        bucket = s3.Bucket(bucket_name)
        directories = set()

        for obj in bucket.objects.all():
            parts = obj.key.split('/')
            if len(parts) > 1:
                directories.add(parts[0])

        print(f"Dossiers trouvés dans le bucket {bucket_name} :")
        for directory in directories:
            print(directory)

        return directories
    except NoCredentialsError:
        print("Les identifiants n'ont pas été trouvés ou sont incorrects.")
    except ClientError as e:
        print(f"Erreur Client lors de la liste des dossiers : {e}")
    except Exception as e:
        print(f"Erreur inattendue lors de la liste des dossiers : {e}")


def upload_file_to_s3(local_file_path, bucket_name, s3_file_path, access_key, secret_key, endpoint_url):
    try:
        if not os.path.isfile(local_file_path):
            print(f"Erreur: Le fichier spécifié est introuvable: '{local_file_path}'")
            return

        s3_client = boto3.client(
            's3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            endpoint_url=endpoint_url
        )

        s3 = boto3.resource(
            's3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            endpoint_url=endpoint_url
        )
        bucket = s3.Bucket(bucket_name)
        if not bucket.creation_date:
            print(f"Le bucket {bucket_name} n'existe pas ou les identifiants sont incorrects.")
            return

        # Configuration pour suivre la progression
        config = TransferConfig(use_threads=True)
        transfer = S3Transfer(client=s3_client, config=config)

        # Fonction de callback po ur tqdm
        def upload_progress(chunk):
            progress.update(chunk)

        # Taille du fichier
        file_size = os.path.getsize(local_file_path)

        # Barre de progression
        with tqdm(total=file_size, unit='B', unit_scale=True, desc=local_file_path, ascii=True) as progress:
            transfer.upload_file(local_file_path, bucket_name, s3_file_path, callback=upload_progress)

        print(f"Le fichier {local_file_path} a été uploadé avec succès à {s3_file_path} dans le bucket {bucket_name}.")

        # Suppression du fichier local après l'upload réussi
        # os.remove(local_file_path)

    except NoCredentialsError:
        print("Les identifiants n'ont pas été trouvés ou sont incorrects.")
    except ClientError as e:
        print(f"Erreur Client lors de l'upload : {e}")
    except Exception as e:
        print(f"Erreur inattendue lors de l'upload : {e}")


bucket_name = 'cinaf'
access_key = '391ce0ea525cd4f7f15fbde0df3f7149'
secret_key = 'c62bc6b89cb3d0e4ed34017d2368ca78'
endpoint_url = 'https://s3.advanced.host'


def uploadFileToS3(local_file_path, s3_file_path):
    upload_file_to_s3(local_file_path, bucket_name, s3_file_path, access_key, secret_key, endpoint_url)
