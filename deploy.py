#!/usr/bin/env python3
"""Run on a Proxmox node as root. Dry-run by default."""
import argparse, json, pathlib, re, subprocess, os, shlex

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--vmid',type=int,required=True); p.add_argument('--name',required=True)
 p.add_argument('--image',type=pathlib.Path,required=True); p.add_argument('--storage',required=True)
 p.add_argument('--snippet',required=True,help='Existing Proxmox volume ID, e.g. local:snippets/uag-900.yaml')
 p.add_argument('--nic',action='append',default=None,help='Isolated bridge[,tag=N]; default vmbr10')
 p.add_argument('--cores',type=int,default=2); p.add_argument('--memory',type=int,default=4096)
 p.add_argument('--apply',action='store_true'); p.add_argument('--start',action='store_true')
 a=p.parse_args()
 a.nic=a.nic or ['vmbr10']
 if not 100<=a.vmid<=999999999 or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,31}',a.name): p.error('Invalid VMID/name')
 if len(a.nic)!=1 or a.cores<1 or a.memory<4096: p.error('Invalid NIC count or sizing')
 if a.start and not a.apply: p.error('--start requires --apply')
 for s in [a.storage]:
  if not re.fullmatch(r'[\w-]+',s): p.error('Invalid storage ID')
 if not re.fullmatch(r'[\w-]+:snippets/[\w.-]+',a.snippet): p.error('Invalid snippet volume ID')
 for nic in a.nic:
  if not re.fullmatch(r'[\w.-]+(?:,tag=[0-9]{1,4})?',nic): p.error('Invalid NIC syntax')
  if ',tag=' in nic and not 1<=int(nic.split('=')[1])<=4094: p.error('Invalid VLAN')
 vm=str(a.vmid)
 def run(*args, capture=False):
  if not capture: print(shlex.join(args),flush=True)
  if a.apply or capture: return subprocess.check_output(args,text=True) if capture else subprocess.run(args,check=True)
 if a.apply:
  if os.geteuid()!=0: p.error('Run as root on Proxmox')
  if not a.image.is_file(): p.error('Image missing')
  info=json.loads(run('qemu-img','info','--output=json',str(a.image),capture=True))
  if info.get('format')!='qcow2' or info.get('backing-filename'): p.error('Expected standalone QCOW2')
  resources=json.loads(run('pvesh','get','/cluster/resources','--type','vm','--output-format','json',capture=True))
  if any(int(x['vmid'])==a.vmid for x in resources): p.error('VMID already exists')
  snippet=pathlib.Path(run('pvesm','path',a.snippet,capture=True).strip())
  if not snippet.is_file() or not snippet.read_text().startswith('#cloud-config') or '/var/lib/cloud/instances/user-data.txt' not in snippet.read_text(): p.error('Missing/invalid snippet')
  if snippet.stat().st_mode & 0o077: p.error('Snippet must be private (chmod 600)')
 create=['qm','create',vm,'--name',a.name,'--cores',str(a.cores),'--memory',str(a.memory),'--cpu','host','--bios','seabios','--scsihw','virtio-scsi-single','--ostype','l26','--agent','1','--smbios1','manufacturer=RedHat,product=OpenShift']
 for i,nic in enumerate(a.nic): create.extend([f'--net{i}',f'virtio,bridge={nic}'])
 run(*create)
 run('qm','set',vm,'--scsi0',f'{a.storage}:0,import-from={a.image.resolve()}')
 run('qm','set',vm,'--ide2',a.storage+':cloudinit','--citype','nocloud','--cicustom','user='+a.snippet,'--boot','order=scsi0')
 run('qm','cloudinit','update',vm)
 if a.start: run('qm','start',vm)
 print('Done. VM left stopped unless --start was requested.' if a.apply else 'Dry run only; no VM created.')
if __name__=='__main__': main()
