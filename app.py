import os
import threading
import uuid
import subprocess
import shutil
from flask import Flask, request, jsonify,send_from_directory, render_template, session
from flask_socketio import SocketIO, emit
from lib.s3 import uploadFileToS3
import json
import ulid
from db.models import create_database_if_not_exists
from flask_sqlalchemy import SQLAlchemy




app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", max_http_buffer_size= 1024 * 1024 * 1024 * 1024)
app.config["SQLALCHEMY_DATABASE_URI"] = "mysql://root:@localhost:3306/alchemy"
db = SQLAlchemy(app)


    

class Formats(db.Model):
    __tablename__ = 'formats'
    id = db.Column(db.String(26), primary_key=True)
    upload_state_id = db.Column(db.String(26), db.ForeignKey('upload_states.id'))
    resolution = db.Column(db.JSON)
    isOriginal = db.Column(db.Boolean)
    extension = db.Column(db.String(10))
    size = db.Column(db.String(50))
    path = db.Column(db.String(255))

class UploadState(db.Model):
    __tablename__ = 'upload_states'
    id = db.Column(db.String(26), primary_key=True)
    file_id = db.Column(db.String(36), nullable=False)
    chunk_number = db.Column(db.Integer, nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    total_chunks = db.Column(db.Integer, nullable=False)
    folder_path = db.Column(db.String(255), nullable=False)
    format = db.relationship('Formats', backref='upload_states', lazy=True) 

def createTable():
    try:
        with app.app_context():
            db.create_all()  
            print("Tables crées avec success")
    except Exception as err:
        print(f"Error: {err}")
create_database =create_database_if_not_exists('alchemy', 'localhost', 'root', '')
create = createTable()
#path sql alchemy mysql://username:password@host:port/database_name


# Dossiers de stockage 
UPLOAD_FOLDER = 'uploads'
CONTENT_FOLDER = 'tests/contents'     
BASE_PATH_LINK = 'https://cdn.cinaf.tv/media=hls/multi='
RESOLUTIONS = {
    'FHD': '1920x1080', 
    'HD': '1280x720',
    'MD': '854x480', 
    'SD': '320x180'     
}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = 'votre_clé_secrète'  # Clé secrète pour la gestion des sessions

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)



def save_to_db(filename, folder_path, file_id, chunk_number, total_chunks):
    try:
     with app.app_context(): 
        ulid_id = str(ulid.new())
        new_upload_state = UploadState(

            id=ulid_id,
            filename=filename,
            folder_path=folder_path,
            file_id=file_id,
            chunk_number=chunk_number, 
            total_chunks=total_chunks
            
        )
        db.session.add(new_upload_state ) 
        db.session.commit()
        print(f" l'enregistrement des données reussit")
        return new_upload_state.id
    except Exception as e :
        db.session.rollback()
        print(f"Erreur lors de l'enregistrement des données : {e}")
        return {"error": str(e)}

 
def save_format_to_db(video_file_id, resolution, is_original, extension, size, path):
    try:
     with app.app_context():
        ulid_id = str(ulid.new())
        new_format = Formats(
            id=ulid_id,
            video_files_id=video_file_id, 
            resolution = json.dumps(resolution),
            isOriginal = int(is_original),    
            extension = extension,
            size = size,
            path = path
        )
        db.session.add(new_format)
        db.session.commit()
        print(f" l'enregistrement des données reussit")
        return {"success":True,}
    except Exception as e :
        db.session.rollback()
        print(f"Erreur lors de l'enregistrement des données : {e}")
        return {"error": str(e)}



def getChunkFolder(filename):
    return os.path.join(UPLOAD_FOLDER, f"{filename}-folder")

def save_chunk(data, filename, chunk_number):
    chunk_folder = getChunkFolder(filename)
    if not os.path.exists(chunk_folder):
        os.makedirs(chunk_folder, 0o711)
    chunk_path = os.path.join(chunk_folder, f"{chunk_number} ")
    with open(chunk_path, "wb") as f:
        f.write(data)
    print(f"Chunk {chunk_number} for {filename} saved.")
   

@socketio.on('pause_upload')
def pause_upload(data):
    filename = data['filename']
    session['paused_uploads'][filename] = True
    print(f"{filename} is paused") 
    emit('response-' + filename, {'status': 'paused'})

# @socketio.on('resume_upload')
# def resume_upload(data):
#     filename = data['filename']
#     session['paused_uploads'][filename] = False
#     session['resume_upload'][filename] = True
#     emit('response-' + filename, {'status': 'resumed'})
def resume_upload(data):
    file_id = data['file_id']
    upload_state = UploadState.query.filter_by(file_id=file_id).first()
    if upload_state:
        next_chunk_number = upload_state.chunk_number + 1
        emit('next_chunk', {'chunkNumber': next_chunk_number})
    else:
        # Erreur téléchargement pour ce fichier
        return

@socketio.on('cancel_upload')
def cancel_upload(data):
    filename = data['filename']

    if 'canceled_uploads' not in session:
        session['canceled_uploads'] = {}
        session['canceled_uploads'][filename] = True

    chunk_folder = getChunkFolder(filename)
    shutil.rmtree(chunk_folder, ignore_errors=True)
    emit('response-' + filename, {'status': 'canceled'})

def getS3Folder(data):
    contentType = data['movieType']
    array_data = [CONTENT_FOLDER, contentType + 's',  data['name']]
    if contentType == 'serie':
        if 'season' in data:
            array_data.append('SAISON' + data['season'] )
        array_data.append('EPISODE' + data['episode'] )
    array_data.append(data['context'] )
    name = data['filename']
    name = str(uuid.uuid4())
    if data['context'] == 'teaser':
      array_data.append(name)
    print(f"{contentType}")
    resultfolder = '/'.join(array_data)
    return resultfolder
   


#https://cdn.cinaf.tv/media=hls/multi=1920x1080:FHD,1280x720:HD,854x480:MD,320x180:SD/contents/series/{name}/saison1/episode1/teasers/hash/_TPL_.mp4.m3u8
def getResolutionsPath(resolutions):
    paths = []
    for resolution in resolutions:    
        paths.append(RESOLUTIONS[resolution] + ':' + resolution)
    resultresolution = ','.join(paths)
    return resultresolution


@socketio.on('upload_chunk')
def handle_chunk(data):
    filename = data['filename']
    file_id = data['file_id']
    chunk_number = data['chunkNumber']
    total_chunks = data['totalChunks']
    compress = data.get('compress', False)
    resolutions = data.get('resolutions', [])

    # Initiation 
    folder_path = os.path.join(UPLOAD_FOLDER, filename.split('.')[0])
    os.makedirs(folder_path, exist_ok=True) 
    
    upload_state = UploadState.query.filter_by(file_id=file_id).first()

    if upload_state:
        if  chunk_number <  upload_state.chunk_number + 1: 
            return  
    else:
     with app.app_context():
        ulid_id = str(ulid.new())
        upload_state = UploadState(
            id=ulid_id,
            filename=filename,
            folder_path=folder_path,
            file_id=file_id,
            chunk_number=chunk_number, 
            total_chunks=total_chunks)
        db.session.add(upload_state)
        db.session.commit()
        print(f'filename save to db: {filename}')
    


    # Save the chunks  and update the dowload   
    save_chunk(data['data'], filename, chunk_number)

    # update upload_state to db 
    upload_state.chunk_number = chunk_number
    db.session.commit()
    
    # combime the total chunks
    if chunk_number + 1 == total_chunks:
        combined_path = combine_chunks(total_chunks, filename)
        if combined_path is None:
            print(f"Error: unable to combine chunks for {filename}") 
            return
        # folder_path = os.path.join(UPLOAD_FOLDER, filename.split('.')[0])
        # os.makedirs(folder_path, exist_ok=True) 
        # Vérifier si le fichier existe déjà et le supprimer
        destination_path = os.path.join(folder_path, os.path.basename(combined_path))
        if os.path.exists(destination_path):
            os.remove(destination_path)
        shutil.move(combined_path, destination_path)
        #save_to_db(filename=filename, folder_path=folder_path, file_id=file_id)
        #  original file to S3
        s3_directory = getS3Folder(data) + '/' + filename
        print(f"{s3_directory}")
        uploadFileToS3(destination_path, s3_directory)

        s3_url = '/'.join([f"{BASE_PATH_LINK}", s3_directory, '_TPL_.'+ filename.split('.')[1]+'.m3u8'])
        emit('originalUrl', {
            'url': s3_url
        })

#/contents/films/name/sources/hd.mp4
#/contents/films/name/trailler/hd.mp4
#/contents/films/name/teasers/hash/hd.mp4
#/contents/series/name/sources/saison1/episode1/hd.mp4
#/contents/series/name/traillers/saison1/hd.mp4
#/contents/series/{name}/teasers/saison1/episode1/hash/hd.mp4
#/contents/series/{name}/teasers/saison1/episode1/hash/_TPL_.mp4.m3u8
#https://cdn.cinaf.tv/media=hls/multi=1920x1080:FHD,1280x720:HD,854x480:MD,320x180:SD/KIGAH/EPISODE_01/KIGAH_EPISODE_01__TPL_.mp4.m3u8
#https://cdn.cinaf.tv/media=hls/multi=1920x1080:FHD,1280x720:HD,854x480:MD,320x180:SD/contents/series/{name}/teasers/saison1/episode1/hash/_TPL_.mp4.m3u8
#https://cdn.cinaf.tv/contents/series/{name}/teasers/saison1/episode1/hash/HD.mp4
#{
#type: 'film',
#context: 'source',
#}
#{
#type: 'serie',
#context: 'source',
#saisonNumber: '1',
#episodeNumber: '1',
#}#
        if compress:
            # hhhhh
            pass

        #arrayResolutions = resolutions if len(resolutions) > 0 else ['180', '240', '360', '480', '720', '1080']

        #convert_video(destination_path, arrayResolutions, folder_path)


        if len(resolutions) > 0:
            convert_video(destination_path, resolutions, folder_path, data)
       
        # Delete the original file
        # os.remove(destination_path)
       
        

              
        # file_data = {
        #     'filename': 'richard',
        #     'type': 'movie',
        #     'context': 'teaser',
        #     'name': 'MADAME_MONSIEUR'
        # }

        # print(f"{getS3Folder(file_data)} : ceci est le print de la fonction")
        # print(f"{getResolutionsPath(['FHD'])} : ceci est le path fourni pour les résolutions")
        
        # getfilefoler= getS3Folder(filename)
        # resolutionPaths3 = getResolutionsPath(resolutions)
#https://cdn.cinaf.tv/media=hls/multi=1920x1080:FHD,1280x720:HD,854x480:MD,320x180:SD/contents/series/{name}/teasers/saison1/episode1/hash/_TPL_.mp4.m3u8
    
       # Generer l'url sur s3

        
                 
        # for resolution in resolutions:
        #     s3_directory = getS3Folder(data)+'/'+resolution+f".{filename.split('.')[1]}"
        #     print(f"{s3_directory}")
        #     uploadFileToS3( destination_path, s3_directory)

        

        
         
        #resolutionPaths3 = getResolutionsPath(resolutions)
        #s3_url = f"{BASE_PATH_LINK}{resolutionPaths3}/{s3_directory}/{filename}/hash/_TPL_.mp4.m3u8"
        #s3_url = '/'.join([f"{BASE_PATH_LINK}{resolutionPaths3}", s3_directory, '_TPL_.'+ filename.split('.')[1]+'.m3u8'])
        
        #uploadFileToS3( destination_path, s3_url)
        

        emit('response-' + filename + str(chunk_number), {
            'status': True,
            'filename': filename,
            'folder_path': folder_path
        })
    else:
        emit('response-' + filename + str(chunk_number), {'status': True, 'filename': filename})

    if 'paused_uploads' not in session:
        session['paused_uploads'] = {}
    session['paused_uploads'][filename] = False

    if session.get('resume_upload', {}).get(filename, False):
        session['resume_upload'][filename] = False
        emit('response-' + filename + str(chunk_number), {
            'status': True,
            'filename': filename,
            'combined_path': combined_path,
            #'audio_path': audio_path,
            'folder_path': folder_path
        })

    

def combine_chunks(total_chunks, filename):
    root, ext = os.path.splitext(filename)
    target_path = os.path.join(UPLOAD_FOLDER, f"{filename}")

    chunk_folder = getChunkFolder(filename)
    print(f"Combining {total_chunks} chunks for {filename}")

    # if not os.path.exists(chunk_folder):
    #     print(f"Error: Chunk folder '{chunk_folder}' not found.")
    #     return

    try:
        with open(target_path, "ab") as target_file:
            for i in range(total_chunks):
                chunk_part = os.path.join(chunk_folder, f"{i}")
                if not os.path.exists(chunk_part):
                    print(f"Error: Chunk {i} for {filename} not found.")
                    return
                with open(chunk_part, "rb") as source_file:
                    target_file.write(source_file.read())
                print(f"Chunk {i} for {filename} written to {target_path}")
                os.remove(chunk_part)
        os.rmdir(chunk_folder)
    except Exception as e:
        print(f"Error: {e}")
    
    
    return target_path


def execute_command(cmd):
    print(f'Executing command: {cmd}')
    subprocess.run(cmd, shell=True)
    print(f'Command completed: {cmd}')



def convert_video(video_file, resolutions, output_dir, data, file_id,chunk_number,total_chunks):
    # Get the video file name without extension
    video_name = os.path.basename(video_file).split('.')[0]

    # Create a folder for the compressed video
    # compressed_folder = os.path.join(output_dir, 'compressed')
    # os.makedirs(compressed_folder, exist_ok=True)

    # Compress the video
    # compressed_video_file = f"{video_name}_compressed.mp4"
    # compressed_video_path = os.path.join(compressed_folder, compressed_video_file)
    # cmd = f"ffmpeg -i {video_file} -c:v libx264 -crf 28 -c:a {compressed_video_path}"
    # execute_command(cmd)

    # Save video to the database
    result = save_to_db(
        filename=video_name,
        folder_path=output_dir, 
        file_id=file_id, 
        chunk_number=chunk_number, 
        total_chunks=total_chunks)
    

   
    # Define the resolutions and corresponding commands
    resolution_map = {
        'SD': {'width': 320, 'height': 180, 'bitrate': 250, 'filename': f'{video_name}_SD.mp4'},
        # '240': {'width': 426, 'height': 240, 'bitrate': 500, 'filename': f'{video_name}_240p.mp4'},
        # '360': {'width': 640, 'height': 360, 'bitrate': 750, 'filename': f'{video_name}_360p.mp4'},
        'MD': {'width': 854, 'height': 480, 'bitrate': 1000, 'filename': f'{video_name}_MD.mp4'},
        'HD': {'width': 1280, 'height': 720, 'bitrate': 1500, 'filename': f'{video_name}_HD.mp4'},
        'FHD': {'width': 1920, 'height': 1080, 'bitrate': 2250, 'filename': f'{video_name}_FHD.mp4'}
    }
    # file_data = {
    #         'filename': 'richard',
    #         'type': 'movie',
    #         'context': 'teaser',
    #         'name': 'MADAME_MONSIEUR'
    # }
    # contentType = data['type']

    # Convert the compressed video to different resolutions
    commands = []
    for resolution in resolutions:
        if resolution in resolution_map:
            res = resolution_map[resolution]
            output_file = os.path.join(output_dir, res['filename'])
            cmd = (
                f'ffmpeg -i {video_file} -vf scale={res["width"]}:{res["height"]} '
                f'-b:v {res["bitrate"]}k -c:a copy {output_file}'
            )
            commands.append(cmd)

    # Execute all commands in parallel
    threads = []
    for cmd in commands:
        thread = threading.Thread(target=execute_command, args=(cmd,))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()
    
    # Save format details to the database
    for resolution in resolutions:
        if resolution in resolution_map:
            res = resolution_map[resolution]
            format_path = os.path.join(output_dir, res['filename'])
            s3_directory = getS3Folder(data) + '/' + resolution + f".{output_file.split('.')[1]}"
            print(f"{s3_directory}")
            uploadFileToS3(format_path, s3_directory)
            with open(format_path, 'rb'):
                file_size = os.path.getsize(format_path)
                save_format_to_db(
                    video_file_id=result,
                    resolution={'width': res['width'], 'height': res['height']},
                    is_original=0  ,
                    extension='mp4',
                   size= str(file_size),
                   path= format_path,
                )
                # Emit a message to the client with the URL of the converted 
            resolutionPaths3 = getResolutionsPath(resolutions)
            s3_url = '/'.join([f"{BASE_PATH_LINK}{resolutionPaths3}", s3_directory, '_TPL_.'+ output_file.split('.')[1]+'.m3u8'])
            emit('convertedUrl', {
                'url': s3_url,
                'resolution': resolution
            })
            # s3_directory = getS3Folder(data)+'/'+resolution+f".{output_file.split('.')[1]}"
            # print(f"{s3_directory}")
            # uploadFileToS3( format_path, s3_directory)
            #s3_url = '/'.join([f"{BASE_PATH_LINK}{resolution}", s3_directory, '_TPL_.'+ output_file.split('.')[1]+'.m3u8'])
       
def extract_audio(video_path, output_dir):
    audio_filename = os.path.splitext(os.path.basename(video_path))[0] + '.mp3'
    audio_path = os.path.join(output_dir, audio_filename)

    command = f'ffmpeg -i {video_path} -q:a 0 -map a {audio_path}'
    execute_command(command)

    return audio_path



@app.route('/')
def index():
    return render_template('index.html')

# @app.route('/static/<path:path>')
# def send_static(path):
#     return send_from_directory('static', path)

if __name__ == '__main__':
    socketio.run(app, create_database, create,  debug=True)


    
 