                                                                      

                                                                         
                                                                             
                                                       
   
import math
import struct
import zlib

SCALE, PAD = 6, 48
WIDTH, HEIGHT = 726, 504
BALL = bytes((255, 248, 216))
KITS = {(team, n): bytes((48+n*5, 129+n*5, 235)) if team == 0
        else bytes((235, 55+n*6, 75+n*4)) for team in (0, 1) for n in range(1, 12)}
CALIBRATION = {'width': WIDTH, 'height': HEIGHT, 'left': PAD, 'top': PAD,
               'pitch_width_px': 630, 'pitch_height_px': 408,
               'length_m': 105., 'width_m': 68., 'fps': 20,
               'view': 'fixed top-down; lossless RGB8; calibrated synthetic kits'}
DIGITS = ('111101101101111', '010110010010111', '111001111100111',
          '111001111001111', '101101111001001', '111100111001111',
          '111100111101111', '111001010010010', '111101111101111', '111101111001111')


def chunk(kind, data):
    return struct.pack('!I', len(data))+kind+data+struct.pack('!I', zlib.crc32(kind+data)&0xffffffff)


def encode_png(rgb):
    stride = WIDTH*3
    raw = b''.join(b'\0'+rgb[y*stride:(y+1)*stride] for y in range(HEIGHT))
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('!IIBBBBB', WIDTH, HEIGHT, 8, 2, 0, 0, 0))
            +chunk(b'IDAT', zlib.compress(raw, 2))+chunk(b'IEND', b''))


def decode_png(png):
    if not isinstance(png, bytes) or not png.startswith(b'\x89PNG\r\n\x1a\n') or len(png)>2_000_000:
        raise ValueError('Expected a bounded PNG camera frame')
    pos, data, header, ended = 8, bytearray(), False, False
    while pos+12 <= len(png):
        size = struct.unpack('!I', png[pos:pos+4])[0]
        kind, body = png[pos+4:pos+8], png[pos+8:pos+8+size]
        if pos+size+12>len(png) or zlib.crc32(kind+body)&0xffffffff != struct.unpack('!I', png[pos+8+size:pos+12+size])[0]:
            raise ValueError('Corrupt camera frame')
        if kind == b'IHDR':
            if header or body != struct.pack('!IIBBBBB', WIDTH, HEIGHT, 8, 2, 0, 0, 0):
                raise ValueError('Unsupported camera calibration')
            header = True
        elif not header:raise ValueError('PNG header must precede pixels')
        elif kind == b'IDAT': data.extend(body)
        elif kind == b'IEND':
            if body or pos+12!=len(png):raise ValueError('Unexpected bytes after camera frame')
            ended = True; break
        else: raise ValueError('Unexpected camera metadata/chunk')
        pos += size+12
    if not header or not ended: raise ValueError('Incomplete PNG')
    decoder = zlib.decompressobj()
    raw = decoder.decompress(bytes(data), (WIDTH*3+1)*HEIGHT+1)
    if len(raw)!=(WIDTH*3+1)*HEIGHT or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError('Invalid camera pixel size')
    stride = WIDTH*3+1
    if any(raw[y*stride] for y in range(HEIGHT)):raise ValueError('Unsupported PNG filter')
    return b''.join(raw[y*stride+1:(y+1)*stride] for y in range(HEIGHT))


def disc(rgb, x, y, radius, colour):
    x, y = round(x), round(y)
    for dy in range(-radius, radius+1):
        if not 0<=y+dy<HEIGHT:continue
        dx = int(math.sqrt(radius*radius-dy*dy))
        left, right = max(0, x-dx), min(WIDTH-1, x+dx)
        if right>=left:
            offset=((y+dy)*WIDTH+left)*3
            rgb[offset:offset+(right-left+1)*3] = colour*(right-left+1)


def pixel(rgb, x, y, colour):
    x,y=round(x),round(y)
    if 0<=x<WIDTH and 0<=y<HEIGHT:rgb[(y*WIDTH+x)*3:(y*WIDTH+x)*3+3]=colour


def background():
    rgb=bytearray(bytes((18, 51, 43))*(WIDTH*HEIGHT))
    for y in range(PAD,PAD+409):
        for stripe in range(10):
            left=PAD+stripe*63;offset=(y*WIDTH+left)*3
            rgb[offset:offset+189]=bytes((30, 96+stripe%2*8, 66))*63
    white=bytes((205,225,209))
    for x in range(PAD,PAD+631):
        pixel(rgb,x,PAD,white);pixel(rgb,x,PAD+408,white)
    for y in range(PAD,PAD+409):
        for x in (PAD,PAD+315,PAD+630):pixel(rgb,x,y,white)
    for side in (0,1):
        x=PAD+side*630;edge=x+(99 if side==0 else -99)
        for y in range(PAD+83,PAD+326):pixel(rgb,edge,y,white)
        for xx in range(min(x,edge),max(x,edge)+1):
            pixel(rgb,xx,PAD+83,white);pixel(rgb,xx,PAD+325,white)
    for angle in range(720):
        a=angle*math.pi/360;pixel(rgb,PAD+315+54.9*math.cos(a),PAD+204+54.9*math.sin(a),white)
    return bytes(rgb)


BACKGROUND=background()


def render(players, ball):
    rgb=bytearray(BACKGROUND)
    for p in players:
        x,y=PAD+p['x']*SCALE,PAD+p['y']*SCALE
        disc(rgb,x,y,6,bytes((218,230,235)))
        disc(rgb,x,y,5,KITS[p['team'],p['number']])
        digits=str(p['number']);left=round(x)-(len(digits)*4-1)//2
        for j,d in enumerate(digits):
            for i,on in enumerate(DIGITS[int(d)]):
                if on=='1':pixel(rgb,left+j*4+i%3,round(y)-2+i//3,bytes((14,30,40)))
    disc(rgb,PAD+ball[0]*SCALE,PAD+ball[1]*SCALE,3,bytes((10,25,35)))
    disc(rgb,PAD+ball[0]*SCALE,PAD+ball[1]*SCALE,2,BALL)
    return encode_png(bytes(rgb))
