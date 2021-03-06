import urllib
import json
import html
import xml.etree.ElementTree as ET
from collections import namedtuple
from flask import Blueprint
from flask import request, abort
from flask import jsonify
from .videos import videos_list_by_id, addVideo
from .db import *


mod = Blueprint('caption', __name__)
TRACK_KEYS = 'id name lang_original lang_translated lang_default'

Track = namedtuple('Track', TRACK_KEYS)
Line = namedtuple('Line', 'start duration text')


@mod.route('/download', methods=['POST'])
def download():
    if not request.data:
        abort(400)
    jsoninput = json.loads(request.data)
    # print request.data
    data = jsoninput['data']
    string = ""
    for r in data:
        video_id = r['videoId']
        level = r['level']
        row = get_first_data_table("video", "*", "WHERE VideoId=%s" % video_id, "", "", "ORDER BY Id")
        if row is None:
                if getSubtitle(video_id):
                    # print("[+]%s: Done"%video_id)
                    response = videos_list_by_id(video_id)
                    snippet = response['items'][0]['snippet']
                    addVideo(video_id, snippet['categoryId'],
                             snippet['channelId'], snippet['title'], level)
                else:
                    # print("[+]%s: Video not found or doesn't have captions"%video_id)
                    string = ", " + video_id
    return jsonify(error=string)


@mod.route('/subtitle', methods=['GET'])
def searchBySub():
    text = request.args.get('text', default='*', type=str)
    inner_join = "inner join (SELECT  VideoId, Min(Num) AS Num FROM subtitle WHERE Text LIKE '% " + text + " %' OR Text LIKE '%" + text + "' OR Text LIKE '"+text+"%' group by VideoId) AS T on subtitle.VideoId=T.VideoId and subtitle.Num=T.Num"
    print(inner_join)
    rows = getDataTable("subtitle", "*", inner_join, "", "", "")
    data = []
    for r in rows:
        # video = getVideoById(r[1])
        row = get_first_data_table("video", "*", "WHERE Id='%s'" % r[1], "", "", "")
        if row is not None:
            data.append(
                {
                    'video': {
                        'id': row[0],
                        'categoryId': row[1],
                        'channelId': row[2],
                        'title': row[3],
                        'level': row[4]
                    },
                    'sub': {
                        'id': r[0],
                        'videoId': r[1],
                        'num': r[2],
                        'start': r[3],
                        'end': r[4],
                        'text': html.unescape(r[5])
                    }
                })
    return jsonify(listVideoSub=data)


@mod.route('/video', methods=['GET'])
def searchSubByVideo():
    text = request.args.get('videoId', default='*', type=str)
    rows = getDataTable("subtitle", "*", "WHERE VideoId='%s'" % text,
                        "", "", "ORDER BY Num")
    data = []
    for r in rows:
        data.append({
            'id': r[0],
            'videoId': r[1],
            'num': r[2],
            'start': r[3],
            'end': r[4],
            'text': html.unescape(r[5])
        })
    return jsonify(listSub=data)


@mod.route('/delete-all', methods=['GET'])
def delete_all():
    try:
        truncated("subtitle")
    except Exception as e:
        return jsonify(success=False)
    return jsonify(success=True)


def getSubtitle(video_id):
    url = "http://video.google.com/timedtext?lang=en&v="+video_id
    try:
        caption = parse_track(urllib.request.urlopen(url), video_id)
        if caption:
            print("hinh_ct")
            # save_srt(caption, video_id)
    except:
        return False
    return True


def parse_track(track, video_id):
    """Parse a track returned by youtube and return a list of lines."""
    lines = []

    tree = ET.parse(track)
    for element in tree.iter('text'):
        if not element.text:
            continue
        start = float(element.get('start'))
        # duration is sometimes unspecified
        duration = float(element.get('dur') or 0)
        text = element.text
        lines.append(Line(start, duration, text))

    # print lines
    sub = convert_caption(lines, video_id)
    # print sub

    return sub


def convert_caption(caption, video_id):
    """Convert each line in a caption to srt format and return a list."""
    if not caption:
        return
    lines = []
    for num, line in enumerate(caption, 1):
        start, duration = line.start, line.duration
        if duration:
            end = start + duration  # duration of the line is specified
        else:
            if caption[num]:
                end = caption[num].start  # we use the next start if available
            else:
                end = start + 5  # last resort
        # open connect Database
        db = connectDb()

        # use method cursor()
        cursor = connectCursor(db)

        # sql insert database
        sql = """INSERT INTO subtitle(VideoId,
                 Num, Start, End, Text, Lang)
                 VALUES ('%(VideoId)s', %(Num)s, '%(Start)s', '%(End)s', '%(Text)s', '%(Lang)s')""" % \
            {'VideoId': video_id,
             'Num': num,
             'Start': convert_time(start),
             'End': convert_time(end),
             'Text': line.text,
             'Lang': "en"
             }
        # print sql
        try:
            # Thuc thi lenh SQL
            cursor.execute(sql)
            # Commit cac thay doi vao trong Database
            db.commit()
        except:
            # Rollback trong tinh huong co bat ky error nao
            db.rollback()

        # ngat ket noi voi server
        db.close()
        line = u'%(num)i\r\n%(start)s --> %(end)s\r\n%(text)s\r\n\r\n' % \
               {'num': num,
                'start': convert_time(start),
                'end': convert_time(end),
                'text': line.text}
        line = line.replace('&quot;', '"')\
                   .replace('&amp;', '&')\
                   .replace('&#39;', '\'')
        lines.append(line)

    return lines


def convert_time(time):
    """Convert given time to srt format."""
    stime = '%(hours)02d:%(minutes)02d:%(seconds)02d,%(milliseconds)03d' % \
            {'hours': time / 3600,
             'minutes': (time % 3600) / 60,
             'seconds': time % 60,
             'milliseconds': (time % 1) * 1000}
    return stime

