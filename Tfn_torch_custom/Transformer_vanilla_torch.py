import math
import io, os
import textract
import random,wandb
import datasets
from torch import nn
from torch import Tensor
from einops import rearrange, repeat
import math, time, torch #,copy
from typing import List
#from performer_torch import PerformerLM
#from pytorch_model_summary import summary
from inputimeout import inputimeout as inpt
from torchnlp.encoders.text import SubwordEncoder
#from torchtext.utils import download_from_url, extract_archive
#from typing import Tuple, Optional, Any, NoReturn, Union, Literal

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
#device = torch.device("cpu")

torch.autograd.set_detect_anomaly(True)

#scaler = torch.cuda.amp.GradScaler(init_scale=2**3)
autocast = torch.cuda.amp.autocast


file = "all_files"

try:
    retrieve_tokenizer = inpt(prompt="retrieve tokenizer?(default: True):",timeout=15)
    print("")
    if retrieve_tokenizer.lower() in ['0','false','null','none',"no","not"]:
        retrieve_tokenizer = False
    else:
        retrieve_tokenizer = True
except:
    retrieve_tokenizer = True

import jsonlines,zstandard

def handle_jsonl(jsonl_reader, get_meta, autojoin_paragraphs, para_joiner, key='text'):
    for ob in jsonl_reader:
        # naive jsonl where each object is just the string itself, with no meta. For legacy compatibility.
        if isinstance(ob, str):
            assert not get_meta
            yield ob
            continue
        text = ob[key]
        if autojoin_paragraphs and isinstance(text, list):
            text = para_joiner.join(text)
        if get_meta:
            yield text, (ob['meta'] if 'meta' in ob else {})
        else:
            yield text

def read_jsonl(file, get_meta=False, autojoin_paragraphs=True, para_joiner='\n\n', key='text'):
    try:
        with open(file, 'rb') as fh:
            cctx = zstandard.ZstdDecompressor()
            reader = io.BufferedReader(cctx.stream_reader(fh))
            rdr = jsonlines.Reader(reader)
            yield from handle_jsonl(rdr, get_meta, autojoin_paragraphs, para_joiner, key)
    except:
        return None


def list_of_all_files(path:str="./") -> str:
    try:
        super_dirs = os.listdir(path)
    except:
        return [path[:-1]]
    dirs = [path+i+"/" for i in super_dirs]
    files = []
    if len(dirs) > 0:
        for i in dirs:
            files += list_of_all_files(i)
    return files

def file_to_str(file_name_with_path:str,files_not_to_be_included: List[str] = [".vscode/",".git/",".code-workspace",".pdb",".pyc",".gz",".npy",".wav","2003/",".tar",".zip",".pt",".pth",".onnx",".history/","wandb/"]) -> str:
    for i in files_not_to_be_included:
        if (i in file_name_with_path):
            return ""

    try:
        file_text = "".join([i for i in textract.process(file_name_with_path, encoding="utf-8").decode()])
        print("textract",file_name_with_path)
    except:
        try:
            print("python native file opener",file_name_with_path)
            f = "".join([i for i in io.open(file_name_with_path, encoding="utf8")])
            file_text = str(f)
        except:
            return ""
    return file_text

def initialize_tokenizer(target_vacab = 2**15):
    files = []
    string_of_files = ""
    sample = "the quick brown fox jumps over the lazy dog.THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG?!@#$%^&*() ``` `` ~-_+=[{]}\\|\"\' ''' '' \"\"    /*-+.:;/.>,<1234567890\t\n\f\r\v\r "
    sample += " ".join([i for i in sample])
    path = "../"
    files += list_of_all_files(path)

    lst = ['af', 'am', 'ar', 'arq', 'art-x-bork', 'as', 'ast', 'az', 'be', 'bg', 'bi', 'bn', 'bo', 'bs', 'ca', 'ceb', 'cnh', 'cs', 'da', 'de', 'el', 'en', 'eo', 'es', 'et', 'eu', 'fa', 'fi', 'fil', 'fr', 'fr-ca', 'ga', 'gl', 'gu', 'ha', 'he', 'hi', 'hr', 'ht', 'hu', 'hup', 'hy', 'id', 'ig', 'inh', 'is', 'it', 'ja', 'ka', 'kk', 'km', 'kn', 'ko', 'ku', 'ky', 'la', 'lb', 'lo', 'lt', 'ltg', 'lv', 'mg', 'mk', 'ml', 'mn', 'mr', 'ms', 'mt', 'my', 'nb', 'ne', 'nl', 'nn', 'oc', 'pa', 'pl', 'ps', 'pt', 'pt-br', 'ro', 'ru', 'rup', 'sh', 'si', 'sk', 'sl', 'so', 'sq', 'sr', 'srp', 'sv', 'sw', 'szl', 'ta', 'te', 'tg', 'th', 'tl', 'tlh', 'tr', 'tt', 'ug', 'uk', 'ur', 'uz', 'vi', 'zh', 'zh-cn', 'zh-tw']
    years = ['2014','2015','2016']
    for lang in lst:
        for year in years:
            try:
                tmp = datasets.load_dataset("ted_talks_iwslt",language_pair=('en',lang),year=year,cache_dir="./.data/huggingface_datasets/")
                for key in tmp.keys():
                    for index in range(len(tmp[key])):
                        for content in tmp[key][index]['translation']:
                            keys = content.keys()
                            string_of_files += "[sos]"+"path:"+i+"|data:[Instruct Mode]translation[Instruct Mode]"+"-->".join([key_+":"+(content[key_]) for key_ in keys])+"[eos]"
            except:
                pass
    try:
        tmp = datasets.load_dataset("pec",'all',cache_dir="./.data/huggingface_datasets/")
        for key in tmp.keys:
            for index in range(tmp[key]):
                string_of_files += "[sos]"+"path:"+i+"|data:[Instruct Mode]dialog reply[Instruct Mode]"+"person 1:"+tmp[key][index]['context']+"responder's persona:"+tmp[key][index]['personas']+"responder"+tmp[key][index]['response']+"[eos]"
    except:
        pass

    for i in files:
        if i.find("jsonl.zst")==-1 and i.find("huggingface_datasets")==-1:
            string_of_files += "[sos]"+"path:"+i+"|data:"+file_to_str(i)+"[eos]"
        elif i.find("huggingface_datasets")!=-1:
            continue
        else:
            print("Jsonl ZST:",i)
            tmp = set()
            for j in read_jsonl(i):
                tmp.union(set([k for k in str(j)]))
            string_of_files += "".join(list(tmp))
            #string_of_files += "".join(["".join(list(set([k for k in "[sos]"+j+"[eos]"]))) for j in read_jsonl(i)])
    set_of_chars = "".join(list(set([i for i in string_of_files])))
    sample += " ".join([i for i in set_of_chars]) + set_of_chars
    sample = "".join(list(set([i for i in sample])))
    print("parsed all chars")
    ### Reserved Token Format => [content] <-- the square braces are required.
    tokenizer = SubwordEncoder(sample,target_vocab_size=target_vacab,reserved_tokens=[
    '[pad]','[unk]','[sos]','[eos]','[copy]','[mask]','[segment_seperator]','[non_text_content]','[/non_text_content]',"[Instruct Mode]","[Null]"
    ],
    eos_index=3,unknown_index=1,padding_index=0)
    vocab_size = tokenizer.vocab_size
    torch.save(tokenizer,"models/tokenizer_"+str(vocab_size)+".tar")
    return tokenizer,vocab_size

if retrieve_tokenizer:
    files = os.listdir("models/")
    tokenizer_files = []
    for i in files:
        if "tokenizer" in i:
            tokenizer_files += [i]
    tokenizer_name = tokenizer_files[0]
    for i in tokenizer_files:
        if int(i[10:-4]) < int(tokenizer_name[10:-4]):
            tokenizer_name = i
    print([[i,j] for i,j in enumerate(tokenizer_files)])
    try:
        inp = int(str(inpt(prompt="index of file to be used(starting from 0):",timeout=15)))   
    except:
        inp = None
    if inp != None: 
        if inp < len(tokenizer_files):
            tokenizer_name = tokenizer_files[inp]
    tokenizer = torch.load("models/"+str(tokenizer_name))
    vocab_size = tokenizer.vocab_size
    for i in range(vocab_size):
        tmp = tokenizer.decode(torch.full((1,),i))
        print(i,":-->",tmp,"<-->",repr(tmp),"<-->",repr(tokenizer.vocab[i]),"<--",sep="")
else:
    try:
        inp = int(str(inpt(prompt="target vocabulary size (default=2**15):",timeout=15)))
        print("")
        if type(inp) != int:
            inp = 2**15
            print("invalid input")
    except:
        inp = 2**15
    tokenizer, vocab_size = initialize_tokenizer(inp)
vocab = tokenizer.vocab

import sys,select
def isdata():
    return select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], [])
    
batch_size: int = 1
eval_batch_size: int = batch_size
mini_batch_size: int = 1

ET: bool = True
ntokens: int = tokenizer.vocab_size # None
emsize: int = 128*8
dim_ffd_mult: int = 4
nlayers: int = 1
repeated_main_layers: int = 32
nhead: int = 8 if ET else 16
dropout: float = (math.pi/10) # 0 <= dropout < ; pi/10 --> 0.3141592653589 : recommended
mem_tokens: int = 1024
bptt: int = (512*8) #- mem_tokens
bptt_deviation: int = 64
seq_scale_down: int = 1#max(2**(int(math.log(2,math.log(2,emsize)))),8)
max_seq_len: int = max(2**14,2**17 // seq_scale_down)
mlp_layers: int = 1
fno_layers: int = 4
modes: int = 1024
width: int = 32
causal: bool = False
attn: str = 'nystrom'
attend_to_self: bool = False
feature_redraw_interval: int = 1024
num_mem_static: int = 1024
num_mem_dyn: int = 2048
mem_kv: int = 1024
local_heads: int = 1
local_heads: int = min(local_heads,nhead)

discriminator: bool = False #INTEGRATED DISCRIMINATOR: DISABLED
progressive_generation: bool = True
use_deepspeed: bool = False
encoder_n_decoder: bool = True

use_sgd: bool = True


def batchify(data, bsz,dim=0):
    if data.size(0) == 2 and len(data.size())==3:
        data = data[0]
    if len(data.size())==2:
        data = data.reshape(-1)
    nbatch = data.size(dim) // bsz
    if nbatch*bsz != data.size(0):
        nbatch += 1
        data = torch.nn.functional.pad(data,(0,(nbatch*bsz)-data.size(0)))
    data = data.narrow(dim, 0, nbatch * bsz)
    data = data.reshape(bsz, -1).contiguous()
    return data

def data_process(raw_text_iter):
  data = tokenizer.encode(raw_text_iter)
  return data.contiguous()

def replace_with_reserved_tokens(data,tok_num=1,only_first_instance=False):
    i = 0
    token = data_process(str(tokenizer.decode(torch.tensor((tok_num,),dtype=torch.long))))
    while True:
        if i>=data.size(0) - token.size(0):
            break
        if ((data[i:i+token.size(0)]==token).sum().item())//token.size(0):
            data = torch.cat((data[:i],torch.full((1,),2,dtype=data.dtype,device=data.device),data[i+token.size(0):]),dim=-1)
            if only_first_instance:
                break
        i+=1
    return data.contiguous()

### Finding all reserved tokens
reserved_tokens = {}
for i in range(vocab_size):
    tmp = tokenizer.decode(torch.full((1,),i))
    if len(tmp) > 0:
        if tmp[0] == "[" and tmp[-1] == "]":
            reserved_tokens[i] = tmp

null_token = None
for i in range(vocab_size):
    tmp = tokenizer.decode(torch.tensor((i,),dtype=torch.long))
    if tmp == '':
        null_token = i
if null_token != None:
    print("Null charachter:",repr(tokenizer.decode(torch.tensor((null_token,),dtype=torch.long))),"<-->",null_token,sep='')

def data_retrieve(data=None,path=None):
    if data != None:
        assert type(data) == str
        for i in data:
            yield i
    elif path != None:
        if "jsonl.zst" in path:
            zst_gen = read_jsonl(path)
            for i in zst_gen:
                yield "[sos]"
                for j in i:
                    yield j
                yield "[eos]"

def random_mask_shuffle_encoder(
                            inp: Tensor,
                            mask: bool = True,
                            mask_percentage: float = 15.0,
                            mask_together_nos: int = 3,
                            mask_continuous_pos: float = -101.0,
                            shuffle: bool = True,
                            shuffle_percentage: float = 15,
                            shuffle_together_nos: int = 3,
                            shuffle_continuous_pos: float = -101
                        ) -> Tensor:
    inp_2: Tensor = inp.clone().detach()
    index_to_be_trained_on = []

    count: int = 0
    together_count: int = 0
    for j in range(inp.size(1)):
        if not shuffle:
            break
        rnd: float = -1
        if shuffle_continuous_pos < -100 or shuffle_continuous_pos > 100:
            rnd: float = random.randint(0,100000)/1000
        elif shuffle_continuous_pos >= -100 and shuffle_continuous_pos <= 100:
            shuffle_together_nos = shuffle_percentage * (inp.size(1)/100)
            if shuffle_continuous_pos < 0:
                if (((j+1)/inp.size(1)) + (shuffle_percentage/100)) >= ((inp.size(1)+((shuffle_continuous_pos/100)*inp.size(1)))/inp.size(1)):
                    rnd: float = shuffle_percentage/2
            else:
                if (j+1)/inp.size(1) >= shuffle_continuous_pos/100:
                    rnd: float = shuffle_percentage/2
        if (((rnd>=0 and rnd<shuffle_percentage) or (together_count<shuffle_together_nos and together_count!=0)) and shuffle and (((count+1)/inp.size(1))<=shuffle_percentage/100)):
            while True:
                r = random.randint(0,inp.size(1)-1)
                if r!=j:
                    break
            if j not in index_to_be_trained_on:
                index_to_be_trained_on.append(j)
            if r not in index_to_be_trained_on:
                index_to_be_trained_on.append(r)
            inp_2[:,j],inp_2[:,r] = inp[:,r],inp[:,j]
            count += 1
            together_count += 1
        elif together_count>=shuffle_together_nos:
            together_count = 0

    count: int = 0
    together_count: int = 0
    for j in range(inp.size(1)):
        rnd: float = -1
        if mask_continuous_pos < -100 or mask_continuous_pos > 100 or mask_continuous_pos==None:
            rnd: float = random.randint(0,100000)/1000
        elif mask_continuous_pos >= -100 and mask_continuous_pos <= 100:
            mask_together_nos = mask_percentage * (inp.size(1)/100)
            if mask_continuous_pos < 0:
                if (((j+1)/inp.size(1)) + (mask_percentage/100)) >= ((inp.size(1)+((mask_continuous_pos/100)*inp.size(1)))/inp.size(1)):
                    rnd: float = mask_percentage/2
            else:
                if ((j+1)/inp.size(1)) >= mask_continuous_pos/100:
                    rnd: float = mask_percentage/2
        if (((rnd>=0 and rnd<mask_percentage) or (together_count<mask_together_nos and together_count!=0)) and mask and (((count+1)/inp.size(1))<=mask_percentage/100)):
            for i in range(inp.size(0)):
                inp_2[i,j] = 5
            if j not in index_to_be_trained_on:
                index_to_be_trained_on.append(j)
            count += 1
            together_count += 1
        elif together_count>=mask_together_nos:
            together_count = 0
    for _ in range(inp_2.size(1)//20):
        rnd = random.randint(0,inp_2.size(1)-1)
        if rnd not in index_to_be_trained_on:
            index_to_be_trained_on.append(rnd)
    index_to_be_trained_on = list(set(index_to_be_trained_on))
    out = inp_2.clone().detach().to(dtype=torch.long).contiguous()
    del(inp_2,inp)
    torch.cuda.empty_cache()
    return out,index_to_be_trained_on

def get_batch(source,j,bptt=bptt,progressive=True,shuffle=True,batch_size_=batch_size,generator=None,prefer_source_over_generator=True,j_0 = -1,replace_all_with_possible_reserved_tokens=False):
    if type(source) == str:
        source = data_process(source)

    for i in reserved_tokens.keys():
        if not replace_all_with_possible_reserved_tokens and i!=2 and i!=3:
            continue
        source = replace_with_reserved_tokens(source,tok_num=i)
    data = None
    data_stream_ended = False
    if ((not prefer_source_over_generator and generator != None) or (generator!=None and j>= source.size(1))):
        data = None
        step = 0
        tmp = ''
        for i in generator:
            if len(tmp) > 0 and i=='[sos]':
                tmp += '[segment_seperator]'
            tmp += i
            step += 1 
            if len(tmp) >= bptt*batch_size_ and step >= batch_size_*bptt_deviation:
                step = 0
                data = data_process(str(tmp))
                if data.size(0) >= bptt*batch_size_:
                    for i in reserved_tokens.keys():
                        if not replace_all_with_possible_reserved_tokens and i!=2 and i!=3:
                            continue
                        data = replace_with_reserved_tokens(data,tok_num=i)
                    if not (data.size(0) >= bptt*batch_size_):
                        continue
                    break
        if data == None:
            data = data_process(str(tmp))
            for i in reserved_tokens.keys():
                if not replace_all_with_possible_reserved_tokens and i!=2 and i!=3:
                    continue
                data = replace_with_reserved_tokens(data,tok_num=i)
        # data = data[data!=null_token] if null_token!=None else data ### problem with whitespace
        data = (batchify(data,batch_size_,-1)).contiguous()

    j_0 = j if (j_0 == -1 and (not prefer_source_over_generator and generator != None)) else j_0
    j -= j_0 if j_0!=-1 else 0
    if data!= None:
        if data.size(-1) > 0:
            source = data.contiguous()
            j=0
            j_0 = -1

    seq_len = min(bptt, source.size(1) - j)
    rnd_shuffle = random.randint(0,1000000)/1000000 if shuffle else 0
    rnd_mask = random.randint(0,1500000000)/100000000
    rnd_mask_together = random.randint(0,int(min(min(4,seq_scale_down)**2 // 2,rnd_mask)))
    rnd = random.randint(0,min((seq_len-1),(bptt//8),(min(8,seq_scale_down)*2)**2))

    if (j+bptt) > source.size(1) and (j_0 != -1 and (not prefer_source_over_generator and generator != None)):
        data_stream_ended = True

    """
    start_text = ["Generate text","learn to generate text","learn to predict","masked language modeling","mlm","continue text","continue input","decorrupt and predict according to input"]
    start_text = start_text[random.randint(0,len(start_text)-1)]
    if random.randint(0,1):
        start_text = torch.cat((torch.full((source.size(0),1),6,dtype=torch.long,device=device),torch.full((source.size(0),1),9,dtype=torch.long,device=device),repeat(data_process(start_text).to(device),"n -> b n",b=source.size(0)),torch.full((source.size(0),1),6,dtype=torch.long,device=device)),dim=1)
    else:
        start_text = torch.full((source.size(0),0),2,dtype=torch.long,device=device)
    start_text = torch.full((source.size(0),0),2,dtype=torch.long,device=device)
    """
    
    if progressive:
        data,index_to_be_trained_on = random_mask_shuffle_encoder(source[:,j:j+seq_len-rnd-1],mask_percentage=rnd_mask,mask_together_nos=rnd_mask_together,mask_continuous_pos=170,shuffle_percentage=rnd_shuffle,shuffle_together_nos=seq_scale_down)
        data = torch.cat((data.to(device),torch.full((data.size(0),rnd),5,dtype=torch.long,device=device)),dim=1).contiguous()
        targets = source[:,j+1:j+seq_len].to(device)
        targets = targets.contiguous()
    else:
        seq_len = min(bptt, source.size(1) - j)
        data,index_to_be_trained_on = random_mask_shuffle_encoder(source[:,j:j+seq_len-rnd],mask_percentage=rnd_mask,mask_together_nos=rnd_mask_together,mask_continuous_pos=170,shuffle_percentage=rnd_shuffle,shuffle_together_nos=seq_scale_down)
        data = torch.cat((data.to(device),torch.full((data.size(0),rnd),5,dtype=torch.long,device=device)),dim=1).contiguous()
        targets = source[:,j:j+seq_len].to(device)
        targets = targets.contiguous()
    torch.cuda.empty_cache()
    return data.to(device),targets.to(device),index_to_be_trained_on,data_stream_ended,j_0

try:
    """
    processed_train_data = torch.load("models/data_"+str(vocab_size)+"/"+file+"_train.tar",map_location=torch.device('cpu'))
    processed_test_data = torch.load("models/data_"+str(vocab_size)+"/"+file+"_test.tar",map_location=torch.device('cpu'))
    processed_val_data = torch.load("models/data_"+str(vocab_size)+"/"+file+"_val.tar",map_location=torch.device('cpu'))

    if 10*processed_test_data.size(1) > processed_train_data.size(1):
        extra_portion = int(((processed_test_data.size(1)/processed_train_data.size(1))*0.66)*processed_test_data.size(1))
        processed_train_data = processed_train_data[:,:extra_portion]
        processed_test_data = processed_test_data[:,extra_portion:]
    """
    processed_train_data = data_process("Hello World!!! This is inference function on the currently trained deep learning model based on the same architecture used by GPT-3 by OpenAI and GPT-J by EleutherAI, namely -> Tranformer Architecture published in 2017 in the paper 'Attention Is All You Need' by Vaswani et. al. which propsed a new")
    processed_test_data = data_process("Hello World!!! This is inference function on the currently trained deep learning model based on the same architecture used by GPT-3 by OpenAI and GPT-J by EleutherAI, namely -> Tranformer Architecture published in 2017 in the paper 'Attention Is All You Need' by Vaswani et. al. which propsed a new")
    processed_val_data = data_process("Hello World!!! This is inference function on the currently trained deep learning model based on the same architecture used by GPT-3 by OpenAI and GPT-J by EleutherAI, namely -> Tranformer Architecture published in 2017 in the paper 'Attention Is All You Need' by Vaswani et. al. which propsed a new")

    processed_train_data = batchify(processed_train_data,batch_size,-1)
    processed_test_data = batchify(processed_test_data,eval_batch_size,-1)
    processed_val_data = batchify(processed_val_data,eval_batch_size,-1)
except Exception as e:
    print(e)
    path = "../"
    files = list_of_all_files(path)
    string_of_files = {"train":"","test":"","val":""}
    txt_type = "train"
    use_huggingface = False

    lst = ['af', 'am', 'ar', 'arq', 'art-x-bork', 'as', 'ast', 'az', 'be', 'bg', 'bi', 'bn', 'bo', 'bs', 'ca', 'ceb', 'cnh', 'cs', 'da', 'de', 'el', 'en', 'eo', 'es', 'et', 'eu', 'fa', 'fi', 'fil', 'fr', 'fr-ca', 'ga', 'gl', 'gu', 'ha', 'he', 'hi', 'hr', 'ht', 'hu', 'hup', 'hy', 'id', 'ig', 'inh', 'is', 'it', 'ja', 'ka', 'kk', 'km', 'kn', 'ko', 'ku', 'ky', 'la', 'lb', 'lo', 'lt', 'ltg', 'lv', 'mg', 'mk', 'ml', 'mn', 'mr', 'ms', 'mt', 'my', 'nb', 'ne', 'nl', 'nn', 'oc', 'pa', 'pl', 'ps', 'pt', 'pt-br', 'ro', 'ru', 'rup', 'sh', 'si', 'sk', 'sl', 'so', 'sq', 'sr', 'srp', 'sv', 'sw', 'szl', 'ta', 'te', 'tg', 'th', 'tl', 'tlh', 'tr', 'tt', 'ug', 'uk', 'ur', 'uz', 'vi', 'zh', 'zh-cn', 'zh-tw']
    years = ['2014','2015','2016']
    if use_huggingface:
        for lang in lst:
            for year in years:
                try:
                    tmp = datasets.load_dataset("ted_talks_iwslt",language_pair=('en',lang),year=year,cache_dir="./.data/huggingface_datasets/")
                    for key in tmp.keys():
                        for index in range(len(tmp[key])):
                            for content in tmp[key][index]['translation']:
                                keys = content.keys()
                                string_of_files[txt_type] += "[sos][Instruct Mode]translation[Instruct Mode]"+"-->".join([key_+":"+content[key_] for key_ in keys])+"[eos]"
                except:
                    pass
        try:
            tmp = datasets.load_dataset("pec",'all',cache_dir="./.data/huggingface_datasets/")
            for key in tmp.keys:
                for index in range(tmp[key]):
                    txt_type = "train"
                    if key.find('test')!=-1:
                        txt_type = "test"
                    elif key.find('val')!=-1:
                        txt_type = "val"
                    string_of_files[txt_type] += "[sos][Instruct Mode]dialog reply[Instruct Mode] person 1:"+tmp[key][index]['context']+"responder's persona:"+tmp[key][index]['personas']+"responder"+tmp[key][index]['response']+"[eos]"
        except:
            pass

    for i in files:
        txt_type = "train"
        if i.find('test')!=-1:
            txt_type = "test"
        elif i.find("val")!=-1:
            txt_type = "val"
        if i.find("jsonl.zst")==-1 and i.find("huggingface_datasets")==-1:
            string_of_files[txt_type] += "[sos]"+"path:"+i+"|data:"+file_to_str(i)+"[eos]"
        elif i.find("huggingface_datasets")!=-1:
            continue
        else:
            continue
            #string_of_files["zst"] = {txt_type:i} #"".join(["[sos]"+i+"[eos]" for i in read_jsonl(i)])

    train_portion = int(len(string_of_files["train"]) * 0.8)
    test_portion = int(len(string_of_files["train"]) * 0.0625)

    test_sample = string_of_files["train"][:test_portion]
    if "[eos]" not in test_sample[-5:]:
        new_portion = string_of_files["train"][test_portion:]
        test_portion += new_portion.find("[eos]")+5
    test_sample = string_of_files["train"][:test_portion] + string_of_files["test"]

    train_sample = string_of_files["train"][test_portion:train_portion+test_portion]
    if "[eos]" not in train_sample[-5:]:
        new_portion = string_of_files["train"][train_portion:]
        train_portion += new_portion.find("[eos]")+5
    train_sample = string_of_files["train"][:train_portion+test_portion]

    val_sample = string_of_files["train"][train_portion+test_portion:] + string_of_files["val"]

    train_data = data_process(train_sample)
    val_data = data_process(val_sample)
    test_data = data_process(test_sample)

    processed_train_data = batchify(train_data, batch_size)
    processed_val_data = batchify(val_data, eval_batch_size)
    processed_test_data = batchify(test_data, eval_batch_size)

    del(train_data,test_data,val_data,train_sample,test_sample,val_sample)

    if not os.path.exists("models/data_"+str(vocab_size)+"/"):
        os.mkdir("models/data_"+str(vocab_size)+"/")

    torch.save(processed_train_data,"models/data_"+str(vocab_size)+"/"+file+"_train.tar")
    torch.save(processed_test_data,"models/data_"+str(vocab_size)+"/"+file+"_test.tar")
    torch.save(processed_val_data,"models/data_"+str(vocab_size)+"/"+file+"_val.tar")

from scripts.model import TransformerX, Trainer,fetch_optimizer_parameters
torch.cuda.empty_cache()

deepspeed_args = {
  "train_batch_size": batch_size,
  "gradient_accumulation_steps": 1,
  "fp16": {
    "enabled": True,
    "loss_scale": 0.5,
    "initial_scale_power": 16,
    "loss_scale_window": 1000,
    "hysteresis": 2,
    "min_loss_scale": 1
    },
  "gradient_clipping":0.5,
  "zero_optimization": {
    "stage": 3,
    'allgather_partitions': True,
    "allgather_bucket_size":1,
    "reduce_bucket_size":1,
    "offload_param":{
        "device": "nvme",
        "nvme_path":"/home/vbansal21/",
        "buffer_count":5+nlayers,
        "buffer_size":1,
        "max_in_cpu":1e7
        },
    "offload_optimizer": {
        "device": "nvme",
        "nvme_path": "/home/vbansal21/",
        "buffer_count":5+nlayers,
        #"fast_init":True
        },
    "stage3_gather_fp16_weights_on_model_save": True,
    #"stage3_max_live_parameters":1e8,
    #"stage3_max_reuse_distance":1e8,
    "stage3_prefetch_bucket_size":1e6,
        "overlap_comm": True,
        #"contiguous_gradients": True,
        "sub_group_size": 1,
        "stage3_param_persistence_threshold": 1e7,
    },
    "wall_clock_breakdown":True,
    "flops_profiler": {
    "enabled": False,
    "profile_step": 1,
    "module_depth": -1,
    "top_modules": 3,
    "detailed": False
    },
    "activation_checkpointing": {
    "partition_activations": True,
    "cpu_checkpointing": True,
    "contiguous_memory_optimization": False,
    "number_checkpoints": nlayers*2+4,
    "synchronize_checkpoint_boundary": True,
    "profile": False
    }
}
if use_deepspeed:
    import deepspeed

    with deepspeed.zero.Init(mem_efficient_linear=True,remote_device='nvme',config=deepspeed_args,enabled=True):
        #model = PerformerLM(num_tokens=ntokens,max_seq_len=2**17,dim=emsize,depth=nlayers,heads=nhead,causal=True,use_rezero=True,cross_attend=True)
        model = TransformerModel( 
                                ninp=emsize, 
                                nhead=nhead, 
                                nhid=nhid, 
                                nlayers=nlayers,
                                ntoken=ntokens,
                                dropout=dropout,
                                deberta_layers=deberta_layers,
                                repeated_deberta_layers=repeated_deberta_layers,
                                mem_token=mem_tokens,
                                #discriminator=discriminator,
                                seq_scale_down=seq_scale_down,
                                max_seq_len=max_seq_len,
                                full_block_repeat=full_block_repeat,
                                causal=causal,
                                nystrom=nystrom,
                                attend_to_self=attend_to_self,
                                fno_layers=fno_layers,
                                modes=modes,
                                width=width,
                                feature_redraw_interval=feature_redraw_interval,
                                prev_state_len=prev_state_len,
                                prev_state_self_num=prev_state_self_num,
                                local_heads=local_heads,
                                mlp_layers=mlp_layers,
                                encoder_n_decoder=encoder_n_decoder,
                                repeated_main_layers=repeated_main_layers,
                                ET=ET,
                                mem_kv=mem_kv,
                        ).half()
else:
    model = TransformerX(
                            dim_hidden=emsize, 
                            num_heads=nhead, 
                            dim_ffd_mult=dim_ffd_mult, 
                            num_layers=nlayers, 
                            vocab=ntokens, 
                            dropout=dropout,
                            mem_parameters=mem_tokens,
                            max_seq_len=max_seq_len,
                            #discriminator=discriminator,
                            seq_scale_down=seq_scale_down,
                            causal=causal,
                            attn=attn,
                            attend_to_self=attend_to_self,
                            fno_layers=fno_layers,
                            modes=modes,
                            width=width,
                            feature_redraw_interval=feature_redraw_interval,
                            num_mem_static=num_mem_static,
                            num_mem_dyn=num_mem_dyn,
                            num_local_heads=local_heads,
                            mlp_layers=mlp_layers,
                            num_max_hop=repeated_main_layers,
                            ET=ET,
                            mem_kv=mem_kv,
                    ).to(device)

print("Model Parameters: ",len(model),"\n")
torch.cuda.empty_cache()

model.eval()
inp = torch.randint(0,ntokens-1,(batch_size,bptt),dtype=torch.long,device=device)
#model.toggle_vanilla_attn_mechanism(True,True)
if use_deepspeed:
    with autocast():
        out,mem,mem_ctxt = model(inp)
else:
    out,misc_losses = model.forward(inp)
print("raw in:",inp,"\vin size:",inp.size(),"\nraw out:",torch.argmax((out.reshape(-1,ntokens)),dim=-1),"\vout size:",out.size())
print(model.get_avg_inference_time()," seconds.\n")
del(out,misc_losses,inp)

#print(sum(p.numel() for p in model.parameters()))
date_time = str(time.asctime().replace(" ","_")).replace(":","_")
path = "models"+"/model_"+str(emsize)+"_"+str(nlayers)+"_"+str(nhead)+".tar"

criterion = nn.CrossEntropyLoss()
lr = 0.001

if not use_deepspeed:
    if use_sgd:
        if discriminator:
            optimizer = torch.optim.SGD(fetch_optimizer_parameters(model), lr=lr)
            optimizer_disc = torch.optim.SGD(fetch_optimizer_parameters(discriminator_model), lr=lr)
        else:
            optimizer = torch.optim.SGD(fetch_optimizer_parameters(model),lr=lr)
            optimizer_disc = None
    else:
        if discriminator:
            optimizer = torch.optim.Adadelta(fetch_optimizer_parameters(model), lr=lr)
            optimizer_disc = torch.optim.Adadelta(fetch_optimizer_parameters(discriminator_model), lr=lr)
        else:
            optimizer = torch.optim.Adadelta(fetch_optimizer_parameters(model),lr=lr)
            optimizer_disc = None

else:
    optimizer = torch.optim.Adam(model.parameters(),lr=lr,betas=(0.8,0.999),weight_decay=3e-7,eps=1e-8)

step = 0
def lambda_lr(step_,bptt=4096):
    a = 5000000
    b = 1000
    c = 0.0
    multiplier = (bptt/2048)*batch_size

    scale = 2

    def sub_func(step):
        return (((a/b * (multiplier*step) + 1) / ((multiplier*step)**2 + a)) + c)/((step*(multiplier/200))**0.1+1)

    if step_ < 256:
        return (2 - step_/128)*(1/lr)
    else:
        return sub_func(step_)

    if step_<(1024*(1/lr)/(lr*multiplier**(math.pi*2/10))):
        return sub_func(step_)
    elif step_<(2048*(1/lr)/(lr*multiplier**(math.pi*2/10))):
        return sub_func(step_) / (scale * (lr**0.125))
    else:
        return sub_func(step_) / ((scale**2) * (lr**0.25))
#    pseudo_lambda = lambda step: (((a/b * (multiplier*step) + 1) / ((multiplier*step)**2 + a)) + c)/((step*(multiplier/200))**0.1+1)
#    lambda_1 = lambda step: (pseudo_lambda(step) if step<(1024/(multiplier**(math.pi*2/10))) else (pseudo_lambda(step)/25 if step<(2048/(multiplier**(math.pi*2/10))) else pseudo_lambda(step)/625))

scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer=optimizer,lr_lambda=lambda_lr)
scheduler_disc = torch.optim.lr_scheduler.LambdaLR(optimizer=optimizer_disc,lr_lambda=lambda_lr) if discriminator else None

load_optimizer = bool(use_sgd and True)
load_scheduler = bool(True and load_optimizer)
load_step_number = True
load_tokenizer = True
epoch = 0
best_val_loss = float("inf")

resume_batch = 0
log_interval = 32768
epochs = 2

import matplotlib.pyplot as plt
plt.ion()
plt.plot([lambda_lr(i)*lr for i in range(max(2000,int((processed_train_data.size(1)*epochs) / (bptt*batch_size))))])
plt.draw()
plt.pause(20.0)
plt.close()
plt.plot([lambda_lr(i)*lr for i in range(255,255+max(100000,int((processed_train_data.size(1)*epochs) / (bptt*batch_size))))])
#plt.show(block=False)
plt.draw()
plt.pause(20.0)
plt.close()
del(plt)

train_eval_event = [date_time]

if use_deepspeed:
    model,optimizer,_,scheduler = deepspeed.initialize(model=model,optimizer=optimizer,lr_scheduler=scheduler, config_params=deepspeed_args)

best_model = model

project_name = "Tfn_X"

def wandb_init():
    wandb.init(project=project_name,config={
        "ntokens":ntokens,
        "d_model":emsize,
        "dim_ffd_mult":dim_ffd_mult,
        "layers":nlayers,
        "heads":nhead,
        "dropout":dropout,
        "memory_tokens":mem_tokens,
        "total_epochs":epochs,
        "Sequence_length":bptt,
        "max_seq_len":max_seq_len,
        "seq_scale_down":seq_scale_down,
        "discriminator":discriminator,
        "Number of Parameters":len(model),
        "Progressive generation training":progressive_generation,
        "use_sgd":use_sgd,
        "causal":causal,
        "attn":attn,
        "attend_to_self":attend_to_self,
        "fno_layers":fno_layers,
        "modes":modes,
        "width":width,
        "feature_redraw_intervel":feature_redraw_interval,
        "local_heads":local_heads,
        "mlp_layers":mlp_layers,
        'num_mem_static':num_mem_static,
        'num_mem_dyn':num_mem_dyn,
    },
    resume=True,
    force=False,
    save_code=True
    )

wandb_init()

#wandb.watch(model,criterion=criterion,log_freq=20)


try:
    try:
        checkpoint_ = torch.load(path, map_location=device)
    except:
        _,checkpoint_ = model.load_checkpoint(path,)

    epoch = checkpoint_['epoch']
    best_val_loss = checkpoint_['best_val_loss']
    if load_tokenizer:
        vocab = checkpoint_['vocab']
        tokenizer = checkpoint_['tokenizer']
    
    try:
        model.load_state_dict(checkpoint_['model_state_dict'],strict=False)
        model = checkpoint_['model'].to(device)
    except:
        try:
            model = checkpoint_['model']
        except Exception as e:
            print("Exception",e)
            
    if load_optimizer:
        optimizer.load_state_dict(checkpoint_['optimizer_state_dict'])
        if discriminator:
            optimizer_disc.load_state_dict(checkpoint_['optimizer_disc_state_dict'])
    else:
        if discriminator:
            for p in model.discriminator.parameters():
                p.requires_grad_(False)
            optimizer = torch.optim.SGD(filter(lambda p: p.requires_grad, model.parameters()), lr=lr)
            for p in model.parameters():
                p.requires_grad_(False)
            for p in model.discriminator.parameters():
                p.requires_grad_(True)
            optimizer_disc = torch.optim.SGD(filter(lambda p: p.requires_grad, model.parameters()), lr=lr)
            for p in model.parameters():
                p.requires_grad_(True)
        else:
            for p in model.parameters():
                p.requires_grad_(True)
            optimizer = torch.optim.SGD(model.parameters(),lr=lr)

            
    step = checkpoint_['step_number'] if load_step_number else step

    if load_scheduler:
        scheduler.load_state_dict(checkpoint_['scheduler_state_dict'])
        if discriminator:
            scheduler_disc.load_state_dict(checkpoint_['scheduler_disc_state_dict'])

    else:
        scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer=optimizer,lr_lambda=lambda_lr)
        if discriminator:
            scheduler_disc = torch.optim.lr_scheduler.LambdaLR(optimizer=optimizer_disc,lr_lambda=lambda_lr)

    try:
        resume_batch = checkpoint_['resume_batch']
        train_eval_event = checkpoint_['train_eval_events'] + [date_time]
    except Exception as e:
        print("Exception",e)
        
    try:
        best_model.load_state_dict(checkpoint_['best_model_state_dict'],strict=False)
        best_model = best_model.to(torch.device('cpu'))
    except Exception as e:
        try:
            best_model = checkpoint_['best_model'].to(torch.device('cpu'))
        except Exception as f:
            print("Exception",e,f)
    del(checkpoint_)
    torch.cuda.empty_cache()
except Exception as e:
    print("Exception",e)
    pass

if best_model==None:
    best_model=model

model.to(device)

#inp = torch.zeros([1,bptt],dtype=torch.long).to(device)
#print(summary(model, inp,None,None,None,None,False,False,True,discriminator))

# TODO: Setup 'curses' module to print colored text for inference output
#import curses
def inference(text,*args,size=128,eval_model = model,append_eos_at_end=False,append_sos_at_start=True,**kwargs):
    eval_model.eval()
    eval_model = eval_model.to(device)
    torch.cuda.empty_cache()
    if append_eos_at_end:
        if append_sos_at_start:
            text_input = torch.cat((torch.full(tuple([1,1]),2),data_process(text).unsqueeze(0),torch.full(tuple([1,size]),5),torch.full(tuple([1,1]),3)),dim=1).to(device)
        else:
            text_input = torch.cat((data_process(text).unsqueeze(0),torch.full(tuple([1,size]),5),torch.full(tuple([1,1]),3)),dim=1).to(device)
    else:
        if append_sos_at_start:
            text_input = torch.cat((torch.full(tuple([1,1]),2),data_process(text).unsqueeze(0),torch.full(tuple([1,size]),5)),dim=1).to(device)
        else:
            text_input = torch.cat((data_process(text).unsqueeze(0),torch.full(tuple([1,size]),5)),dim=1).to(device)

    for i in reserved_tokens.keys():
        text_input = replace_with_reserved_tokens(text_input,tok_num=i)
    if use_deepspeed:
        with autocast():
            out,_ = eval_model(text_input)
    else:
        out,_ = eval_model(text_input)
    out = torch.argmax(out.reshape(-1, ntokens),dim=-1).to(torch.device('cpu'))
    result = tokenizer.decode(out)
    print("Your input:\v",tokenizer.decode(text_input.reshape(-1).to(torch.device('cpu'))))
    print("Model's Output:\v",result)
    print('')
    torch.cuda.empty_cache()
    return str(result)


_ = inference("Hello World!!! This is inference function on the currently trained deep learning model based on the same architecture used by GPT-3 by OpenAI and GPT-J by EleutherAI, namely -> Tranformer Architecture published in 2017 in the paper 'Attention Is All You Need' by Vaswani et. al. which propsed a new")

def evaluate(eval_model, data_source, print_val_loss=False,generator=None):
    eval_model.eval()
    total_loss = 0.
    total_acc = 0.
    single_pass_mem = None
    single_pass_mem_ctxt = None
    stride_size = bptt#-3 if progressive_generation else bptt -3
    data_stream_ended = False
    continue_training = True
    j_1 = -1
    i = 0
    eval_model = eval_model.to(device)
    with torch.no_grad():
        while continue_training:
            if data_stream_ended or ((i-j_1)>data_source.size(1)):
                break
            try:
                torch.cuda.empty_cache()
                data, targets, trainable_index,data_stream_ended,j_1 = get_batch(data_source, i,generator=generator,prefer_source_over_generator=False,j_0 = j_1)
                if use_deepspeed:
                    with autocast():
                        output,_ = eval_model(data,mem = single_pass_mem,context_mem=single_pass_mem_ctxt)
                        total_loss += data.size(1) * criterion(rearrange(output,'b n c -> n c b'), rearrange(targets,'b n -> n b')).item()
                        total_acc += ((torch.argmax(output,dim=-1)) == targets).sum().item()
                else:
                    output,_ = eval_model(data,mem = single_pass_mem,context_mem=single_pass_mem_ctxt)
                    total_loss += data.size(1) * criterion(rearrange(output,'b n c -> n c b'), rearrange(targets,'b n -> n b')).item()
                    total_acc += ((torch.argmax(output,dim=-1)) == targets).sum().item()
            except Exception as e:
                print("Error in evaluation:",e)
                total_loss = total_loss + (total_loss/i)*stride_size
                total_acc = total_acc + (total_acc/i)*stride_size
            i+=stride_size
    val_loss = total_loss / i
    val_acc = total_acc/i
    if print_val_loss:
        print('-' * 110)
        print('valid acc {:3.2f}% | valid loss {:5.3f} | valid ppl {:10.3f}'.format(val_acc*100,val_loss, math.exp(val_loss)))
        print('-' * 110)
    return val_loss, val_acc

def save_model(batch):
    global step
    model.eval()
    best_model.eval()

    if discriminator:
        torch.save(
        {
            'epoch': epoch,
            'model_state_dict': model.state_dict(),
            'model':model,
            'best_model':best_model,
            'best_model_state_dict': best_model.state_dict(),
            'optimizer_state_dict': optimizer.state_dict(),
            'optimizer_disc_state_dict': optimizer_disc.state_dict(),
            'scheduler_state_dict': scheduler.state_dict(),
            'scheduler_disc_state_dict':scheduler_disc.state_dict(),
            'best_val_loss': best_val_loss,
            'vocab': vocab,
            'tokenizer': tokenizer,
            'resume_batch':batch,
            'train_eval_events': train_eval_event,
            'step_number': step
        },
        path
        )
    else:
        torch.save(
        {
            'epoch': epoch,
            'model_state_dict': model.state_dict(),
            'model':model,
            'best_model':best_model,
            'best_model_state_dict': best_model.state_dict(),
            'optimizer_state_dict': optimizer.state_dict(),
            'optimizer_disc_state_dict': None,
            'scheduler_state_dict': scheduler.state_dict(),
            'scheduler_disc_state_dict':None,
            'best_val_loss': best_val_loss,
            'vocab': vocab,
            'tokenizer': tokenizer,
            'resume_batch':batch,
            'train_eval_events': train_eval_event,
            'step_number': step
        },
        path
        )
    """
    ckpt_id = epoch*(processed_train_data.size(-1)//bptt) + batch
    model.save_checkpoint(path,ckpt_id,client_sd = {
        'epoch': epoch,
        'best_model': best_model,
        'optimizer_state_dict': optimizer.state_dict(),
        'scheduler_state_dict': scheduler.state_dict(),
        'best_val_loss': best_val_loss,
        'vocab': vocab,
        'tokenizer': tokenizer,
        'resume_batch':batch,
        'train_eval_events': train_eval_event,
        'step_number': step
    })
    """
    model.train()

"""
def func():
    txt = ''
    t = time.time()
    _t = False
    while 1:
        if time.time()-t > 2.5:
            print(">>>",end='')
            _t = True
            t = time.time()
        while isdata():
            tmp = ''
            tmp = sys.stdin.read(0)
            tmp = sys.stdin.read(1)
            txt += tmp
            print(tmp)
        if "exit" in txt:
            break
        if _t:
            print("")
            _t = False
    return txt
"""

torch.cuda.empty_cache()
def train(resume_batch=0,step_scheduler=1,save_intermediate_intervel=8192,save_intermediate_intervel_time_s=900,optimizer=optimizer,optimizer_disc=optimizer_disc):
    
    global step
    global log_interval
    total_loss = 0.
    total_loss_d = 0.
    total_ppl = 0.
    total_time_per_step = 0.
    start_time = time.time()
    intermediate_save_time = time.time()
    acc = 0
    acc_d = 0
    total_acc = 0
    total_acc_d = 0
    stride_size = bptt#-3 if progressive_generation else bptt -3
    i = 0
    batch = resume_batch
    j_0 = -1
    continue_training = True
    zst_gen = data_retrieve(path="./.data/the_pile/00.jsonl.zst")
    data_stream_ended = False
    while continue_training:
        if data_stream_ended:
            break
        model.train()
        step_time = time.time()
        """
        if resume_batch != None:
            if batch < resume_batch:
                continue
        """
        data, targets, trainable_index, data_stream_ended,j_0 = get_batch(processed_train_data, i,progressive=progressive_generation,batch_size_=batch_size,generator=zst_gen,prefer_source_over_generator=False,j_0=j_0) #Indexed Selective training broken
        trainable_index = None
        torch.cuda.empty_cache()

        if not discriminator:
            outputs,losses,loss,acc,time_ = model.training_step(data,targets,criterion,opt=optimizer,trainable_index=trainable_index,mini_batch_size=mini_batch_size,batch=batch)
        else:
            pass

        # FIX REQUIRED: UNICURSES/THREADING/SYS.STDIN.READLINE()
        if isdata():
            tmp = 0
            print("Save the model(0(continue)/1(raise Keyboard Interrupt and save)/2 (for pausing training)/3 (pause + save))?:\v")
            while True:
                if tmp >= 30:
                    inp = 0
                    break
                tmp += 1
                try:
                    inp: str = inpt(prompt="-->",timeout=10)
                    print("")
                except:
                    pass
                if len(inp) > 0:
                    if inp.isnumeric():
                        try:
                            inp = int(inp)
                            if inp not in [0,1,2,3]:
                                raise "Invalid input, type 0 on prompt to continue"
                            break
                        except Exception as e:
                            print("Invalid input:",e)
            print(inp)
            if inp == 0:
                pass
            elif inp==1:
                if inp:
                    save_model(min(0,batch-1))
                raise KeyboardInterrupt
            elif inp >= 2:
                if inp == 3:
                    save_model(min(0,batch-1))
                pause_time = time.time()
                try:
                    print("\nTo resume,press enter\v")
                    while True:
                        try:
                            if isdata():
                                #print("\nIn-scope of if-else, press escape button(\\x1b),then press enter atleast once, then CTRL-d/^D")
                                #c = inpt(prompt="-->",timeout=15)
                                #print("")
                                #if '\x1b' in c or '^D' in c:
                                while isdata():
                                    c = sys.stdin.read(1)
                                try:
                                    print("\nend?(0/1):\v")
                                    _i = inpt(prompt="",timeout=15)
                                    if len(_i) == 0 or not _i.isnumeric():
                                        _i = inpt(prompt="",timeout=15)
                                    if int(_i):
                                        break
                                except:
                                    continue
                        except EOFError:
                            try:
                                print("\nend?(0/1):\v")
                                _i = inpt(prompt="",timeout=15)
                                if len(_i) == 0 or not _i.isnumeric():
                                    _i = inpt(prompt="",timeout=15)
                                if int(_i):
                                    break
                            except:
                                continue
                        time.sleep(15)
                    """
                    while True:
                        text = "Training Paused since:{:5.2f}s".format(time.time() - pause_time)
                        print(text,end="")
                        print("\b"*len(text),end='')
                    """
                except Exception as e:
                    print("Some Other Exception:\v",str(e))
                finally:
                    print("Training Paused since:{:5.2f}s".format(time.time() - pause_time))
                    pause_time = time.time() - pause_time
                    try:
                        inp = inpt(prompt="Run inference?(1/yes/0/no)\v",timeout=30)
                    except Exception as e:
                        inp = "0"
                    if inp.lower() in ['yes','1']:
                        result = ''
                        while True:
                            try:
                                i = int(inpt("Enter 1 for static inference, 0 for exiting:",timeout=30))
                            except:
                                continue
                            print("")
                            if i == 0:
                                break
                            print("\ninput text for inference,type:-->[eos]<-- at start to end previous result if reccurent (type in multi line text then press CTRL-d/ ^D (press twice if no newline character is type i.e. \\n -> enter/return key) when complete ):\v")
                            inp = '' if i==1 else result
                            tmp = ''
                            while True:
                                tmp += sys.stdin.read()
                                try:
                                    print("\nend?(0/1):\v")
                                    _i = inpt(prompt="",timeout=15)
                                    if len(_i) == 0 or not _i.isnumeric():
                                        _i = inpt(prompt="",timeout=15)
                                    if int(_i):
                                        break
                                except:
                                    continue
                            inp += tmp
                            result = inference(inp)
                    

        total_loss += loss
        total_acc += acc

        tmp_acc = total_acc
        tmp_loss = total_loss

        try:
            ppl = math.exp(losses['loss'])
        except:
            ppl = -1.0

        total_ppl += ppl
        inputs = str("\n".join([tokenizer.decode(k.to(torch.device('cpu'))) for k in data]))
        output = str("\n".join([tokenizer.decode(torch.argmax(k,dim=-1).to(torch.device('cpu'))) for k in outputs['output']]))
        req_targets = str("\n".join([tokenizer.decode(k.to(torch.device('cpu'))) for k in targets]))
        del(data,targets,outputs,losses)
        torch.cuda.empty_cache()

        if ((batch % save_intermediate_intervel == 0 and batch > 0) or ((time.time()-intermediate_save_time) > save_intermediate_intervel_time_s) and batch>(resume_batch + 10)):
            _ = inference("Hello World!!! This is inference function on the currently trained deep learning model based on the same architecture used by GPT-3 by OpenAI and GPT-J by EleutherAI, namely -> Tranformer Architecture published in 2017 in the paper 'Attention Is All You Need' by Vaswani et. al. which propsed a new")
            save_model(batch)
            intermediate_save_time = time.time()
            model.train()

        if (batch % log_interval == 0 and batch != resume_batch):
            cur_loss = total_loss / log_interval
            cur_loss_d = total_loss_d / log_interval
            total_ppl /= log_interval

            _,__ = evaluate(model,processed_val_data,True)

            elapsed = time.time() - start_time
            if discriminator:
                print('| epoch {:3d} | {:5d}/{:5d} batches | '
                    'lr_g {:04.5f} | lr_d {:04.5f} | ms/batch {:08.3f} | acc_g {:3.2f}% | '
                    'loss_g {:5.3f} | acc_d {:3.2f}% | loss_d {:5.3f} | ppl {:10.3f}'.format(
                        epoch, batch, processed_train_data.size(1) // bptt, scheduler.get_last_lr()[0],
                        scheduler_disc.get_last_lr()[0],
                        elapsed * 1000 / log_interval,total_acc*100/log_interval,
                        cur_loss,total_acc_d*100/log_interval,cur_loss_d,total_ppl ))
            else:
                print('| epoch {:3d} | {:5d}/{:5d} batches | '
                    'lr {:04.5f} | ms/batch {:08.3f} | acc {:3.2f}% | '
                    'loss {:5.3f} | ppl {:10.3f}'.format(
                        epoch, batch, processed_train_data.size(1) // bptt, scheduler.get_last_lr()[0],
                        elapsed * 1000 / log_interval,total_acc*100/log_interval,
                        cur_loss,total_ppl ))
            total_loss = 0.
            total_acc = 0.
            total_loss_d = 0.
            total_acc_d = 0.
            total_ppl = 0.
            start_time = time.time()
        total_time_per_step += (time.time() - step_time)
        if step_scheduler != None and batch%mini_batch_size == 0:
            if (batch % step_scheduler == 0 and batch > 0) or (epoch >1 and batch == 0 and processed_train_data.size(1)//bptt < step_scheduler):
                scheduler.step(step)
                if discriminator:
                    scheduler_disc.step(step)
                step += 1
        try:
            if batch%mini_batch_size == 0:
                if discriminator:
                    wandb.log(
                        {
                            "Loss Generator":loss_g,
                            "Total Loss Generator":tmp_loss,
                            "Loss Discriminator":loss_d,
                            "step":step,
                            "Accuracy Generator(Percentage)":acc*100/2,
                            "Total Accuracy Generator(Percentage)":tmp_acc*100/2,
                            "Accuracy Discriminator(Percentage)":acc_d*100/2,
                            "epoch":epoch,
                            "batch":batch,
                            "Perplexity of Generator":ppl,
                            'Learning_Rate':scheduler.get_last_lr()[0],
                            'Time per Step':total_time_per_step/mini_batch_size,
                            "input":wandb.Html(inputs),
                            "output":wandb.Html(output),
                            "target":wandb.Html(req_targets),
                            "avg_inference_time":model.get_avg_inference_time(),
                        }
                    )
                else:
                    wandb.log(
                        {
                            "Loss Generator":loss,
                            "step":step,
                            "Accuracy Generator(Percentage)":acc*100/2,
                            "epoch":epoch,
                            "batch":batch,
                            "Perplexity of Generator":ppl,
                            'Learning_Rate':scheduler.get_last_lr()[0],
                            'Time per Step':total_time_per_step/mini_batch_size,
                            "input":wandb.Html(inputs),
                            "output":wandb.Html(output),
                            "target":wandb.Html(req_targets),
                            "avg_inference_time":model.get_avg_inference_time()
                        },
                        
                    )
                total_time_per_step = 0
        except:
            if batch%mini_batch_size == 0:
                if discriminator:
                    wandb.log(
                        {
                            "Loss Generator":loss_g,
                            "Total Loss Generator":tmp_loss,
                            "Loss Discriminator":loss_d,
                            "step":step,
                            "Accuracy Generator(Percentage)":acc*100/2,
                            "Total Accuracy Generator(Percentage)":tmp_acc*100/2,
                            "Accuracy Discriminator(Percentage)":acc_d*100/2,
                            "epoch":epoch,
                            "batch":batch,
                            "Perplexity of Generator":ppl,
                            'Learning_Rate':scheduler.get_last_lr()[0],
                            'Time per Step':total_time_per_step/mini_batch_size,
                            "input":wandb.Html("<error>"),
                            "output":wandb.Html("<error>"),
                            "target":wandb.Html("<error>"),
                            "avg_inference_time":model.get_avg_inference_time(),
                        }
                    )
                else:
                    wandb.log(
                        {
                            "Loss Generator":loss,
                            "step":step,
                            "Accuracy Generator(Percentage)":acc*100/2,
                            "epoch":epoch,
                            "batch":batch,
                            "Perplexity of Generator":ppl,
                            'Learning_Rate':scheduler.get_last_lr()[0],
                            'Time per Step':total_time_per_step/mini_batch_size,
                            "input":wandb.Html("<error>"),
                            "output":wandb.Html("<error>"),
                            "target":wandb.Html("<error>"),
                            "avg_inference_time":model.get_avg_inference_time()
                        },
                        
                    )
                total_time_per_step = 0
        i+=stride_size
        batch +=1

while True:
    epoch_start_time = time.time()
    train(resume_batch=resume_batch)
    resume_batch = 0
    val_loss, val_acc = evaluate(model, processed_val_data,generator=data_retrieve(path="./.data/the_pile/val.jsonl.zst"))
    print('-' * 110)
    print('| end of epoch {:3d} | time: {:08.3f}s | valid acc {:3.2f}% | valid loss {:5.3f} | '
          'valid ppl {:10.3f}'.format(epoch, (time.time() - epoch_start_time),val_acc*100,
                                     val_loss, math.exp(val_loss)))
    print('-' * 110)

    if val_loss < best_val_loss:
        best_val_loss = val_loss
        best_model = model
        save_model(0)
    if resume_batch==0:
        epoch +=1
    if epoch >= epochs:
        break
model = best_model

test_loss,test_acc = evaluate(best_model,processed_test_data,False,data_retrieve(path="./.data/the_pile/test.jsonl.zst"))
print('=' * 110)
print('| End of training | test acc {:3.2f}% | test loss {:5.3f} | test ppl {:10.3f}'.format(test_acc*100,
    test_loss, math.exp(test_loss)))
print('=' * 110)

inference("Hello World!!! This is inference function on the currently trained model",return_mem=False)
mem = mem_ctxt = None
result = ""
while True:
    i = int(input("Enter 2 for reccurent inference,enter 1 for static inference, 0 for exiting:"))
    if i == 0:
        break
    inp = input("input text, 1 string at a time, for inference:") + result
    mem = None if i==1 else mem
    mem_ctxt = None if i==1 else mem_ctxt
    result,mem, mem_ctxt = inference(inp,reccurent_mem=mem,reccurent_mem_ctxt=mem_ctxt)