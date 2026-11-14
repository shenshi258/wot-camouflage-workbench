"""Final archive mesh-group readback using standard-library parsing only."""
import struct
import zipfile
from resource_graph import parse


def sections(blob):
    if len(blob)<8 or struct.unpack_from('<I',blob)[0]!=0x42A14E65:raise ValueError('网格段容器头无效')
    end=len(blob)-4;size=struct.unpack_from('<I',blob,end)[0];start=end-size
    if start<4:raise ValueError('网格段表越界')
    at=start;offset=4;result={}
    while at<end:
        if at+24>end:raise ValueError('网格段表记录不完整')
        length=struct.unpack_from('<I',blob,at)[0];name_size=struct.unpack_from('<I',blob,at+20)[0]
        next_at=at+24+(name_size+3)//4*4
        if not name_size or next_at>end or offset+(length+3)//4*4>start:raise ValueError('网格段边界无效')
        name=blob[at+24:at+24+name_size].decode('utf-8')
        if name in result:raise ValueError('网格段名重复')
        result[name]=memoryview(blob)[offset:offset+length];offset+=(length+3)//4*4;at=next_at
    if at!=end:raise ValueError('网格段表长度无效')
    return result


def visual_groups(read,name):
    errors=[];checked=0
    try:
        tree=parse(read(name))
        suffix='.visual_processed'if name.endswith('.visual_processed')else'.visual'
        primitive=name[:-len(suffix)]+('.primitives_processed'if suffix=='.visual_processed'else'.primitives')
        streams=sections(read(primitive))
    except Exception as error:return 0,[('file',str(error))]
    for geometry in tree.findall('.//geometry'):
        location='geometry[%s|%s]'%(geometry.findtext('vertices'),geometry.findtext('primitive'))
        try:
            vertices=streams[geometry.findtext('vertices').strip()]
            total=struct.unpack_from('<I',vertices,132 if bytes(vertices[:4])==b'BPVT'else 64)[0]
            indices=streams[geometry.findtext('primitive').strip()]
            count,groups=struct.unpack_from('<II',indices,64)
            width=4 if bytes(indices[:64]).rstrip(b'\0')==b'list32'else 2
            if 72+count*width+groups*16>len(indices):raise ValueError('索引缓冲边界无效')
        except Exception as error:errors.append((location,str(error)));continue
        for group in geometry.findall('primitiveGroup'):
            try:
                number=int(group.text.strip())
                if not 0<=number<groups:raise ValueError('primitiveGroup 超出索引分组范围')
                start,triangles,first,size=struct.unpack_from('<4I',indices,72+count*width+number*16)
                if start+triangles*3>count or first+size>total:raise ValueError('顶点分组范围异常')
                values=indices[72+start*width:72+(start+triangles*3)*width].cast('I'if width==4 else'H')
                if values and(min(values)<first or max(values)>=first+size):raise ValueError('顶点分组范围异常')
                checked+=1
            except Exception as error:errors.append((location+'/group'+str(group.text),str(error)))
    return checked,errors


def audit(path,baseline_read,reverse=None):
    reverse=reverse or {};checked=0;existing=[];introduced=[]
    with zipfile.ZipFile(path)as archive:
        names={n.casefold():n for n in archive.namelist()}
        def read(name):return archive.read(names[('res/'+name).casefold()])
        for entry in archive.infolist():
            name=entry.filename
            if not name.lower().endswith(('.visual_processed','.visual')):continue
            resource=name.removeprefix('res/');source=reverse.get(resource.casefold(),resource)
            count,errors=visual_groups(read,resource);checked+=count
            _,before=visual_groups(baseline_read,source)
            for location,message in errors:
                row=dict(resource=name,location=location,issue=message,preexisting=(location,message)in before)
                (existing if row['preexisting']else introduced).append(row)
    if introduced:raise ValueError('转换后出现新的网格问题：'+str(introduced[:3]))
    return dict(groups_checked=checked,preexisting_group_issues=existing,new_group_issues=[])
