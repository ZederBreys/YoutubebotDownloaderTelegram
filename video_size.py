import yt_dlp

def get_video_info(url : str):
    ydl_opts = {
        'simulate': True,  # Не скачивать, а только получить информацию
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

        if bool(info['is_live']) == True: #Проверка на стрим
            return "streaming", "streaming"

        formats = info.get('formats', [info])
        youtube_id = info['id']

        desired_resolutions = ['360p', '720p', '1080p', '1440p', '2160p']
        audio_only_format = None

        video_quality = {}

        for f in formats:
            resolution = f.get('format_note', 'Unknown resolution')
            format_id = f.get('format_id')
            filesize = f.get('filesize', 0)
            if filesize is None:
                filesize = 0
            filesize_mb = filesize / (1024 * 1024)

            if resolution in desired_resolutions:
                #if resolution not in video_quality or float(video_quality[resolution]['filesize_mb']) > filesize_mb:
                    video_quality[resolution] = {
                        'format_id': format_id,
                        'filesize_mb': f'{filesize_mb:.2f}'
                    }
                
            if f.get('vcodec') == 'none' and f.get('acodec') != 'none':
                audio_only_format = f

            
            if audio_only_format:
                audio_filesize = audio_only_format.get('filesize', 0)
                if audio_filesize is None:
                    audio_filesize = 0
                audio_filesize_mb = audio_filesize / (1024 * 1024)
                
                video_quality['audio'] = {
                    'format_id': audio_only_format.get('format_id'),
                    'filesize_mb': f'{audio_filesize_mb:.2f}'
                }
        else:
            pass
    #Осталвяием только лучше качество
    result_dict = {}

    # Проходим по всем элементам исходного словаря
    for resolution, data in video_quality.items():
        filesize_mb = float(data['filesize_mb'])
        
        # Проверяем, есть ли разрешение уже в результирующем словаре
        if resolution in result_dict:
            # Если есть, сравниваем веса и оставляем меньший
            if filesize_mb < float(result_dict[resolution]['filesize_mb']):
                result_dict[resolution] = data
        else:
            # Если разрешения нет, просто добавляем его
            result_dict[resolution] = data

    return youtube_id, result_dict