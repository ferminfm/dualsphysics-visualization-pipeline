/* Appended to post-qcc C, never parsed by qcc or used as a physics header.
 * Pure lvalue passthrough; compact owned local trace only. OMP must be one.
 * This is an observation draft until the coverage/neutrality gate passes. */
#include <zlib.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>

typedef struct {
  uint64_t sequence;
  int32_t site, role, kind, level, i, j, k, field, di, dj, dk, bc;
  double value;
} AuxOperandRecord;
_Static_assert(sizeof(AuxOperandRecord)==64,"trace record layout must be explicit");
static gzFile aux_stream;
static FILE *aux_metadata;
static int aux_active, aux_completed, aux_fd=-1;
static uint64_t aux_count, aux_reads, aux_writes, aux_escapes;
static AuxOperandRecord aux_buffer[1024];
static unsigned aux_buffer_used;
static char aux_names[4096][96];
static int aux_last_bc[4096];

static void aux_fail(const char *reason) {
  fprintf(stderr,"ERROR AUX_OPERAND_TRACE %s\n",reason);fflush(stderr);exit(86);
}
static void aux_flush(void) {
  if (!aux_buffer_used)return;
  unsigned n=aux_buffer_used*sizeof(AuxOperandRecord);
  if (gzwrite(aux_stream,aux_buffer,n)!=(int)n)aux_fail("write_failed");
  aux_buffer_used=0;
  struct stat s;
  if(fstat(aux_fd,&s))aux_fail("stat_failed");
  if(s.st_size>1073741824LL)aux_fail("compressed_trace_limit_1_GiB");
}
static void aux_emit(AuxOperandRecord record) {
  record.sequence=aux_count++;
  if(aux_count>300000000ULL)aux_fail("record_limit_300_million");
  aux_buffer[aux_buffer_used++]=record;
  if(aux_buffer_used==1024)aux_flush();
}
static void aux_field(int field) {
  if(field<0 || field>=4096 || ! _attribute[field].name)aux_fail("field_identity_invalid");
  const char *name=_attribute[field].name;
  if(strlen(name)>=96 || strchr(name,'"') || strchr(name,'\\'))aux_fail("field_name_encoding");
  int bc=_attribute[field].stencil.bc;
  if(!strcmp(aux_names[field],name) && aux_last_bc[field]==bc)return;
  strcpy(aux_names[field],name);aux_last_bc[field]=bc;
  fprintf(aux_metadata,"{\"event\":\"field_state\",\"sequence\":%llu,\"field\":%d,\"name\":\"%s\",\"bc\":%d,\"io\":%d,\"width\":%d,\"face\":%d,\"third\":%d,\"block\":%d,\"restriction_relative_main\":%llu,\"prolongation_relative_main\":%llu,\"boundary_relative_main\":[",
      (unsigned long long)aux_count,field,name,bc,_attribute[field].stencil.io,_attribute[field].stencil.width,_attribute[field].face,_attribute[field].third,_attribute[field].block,
      _attribute[field].restriction ? (unsigned long long)((uintptr_t)_attribute[field].restriction-(uintptr_t)main) : 0ULL,
      _attribute[field].prolongation ? (unsigned long long)((uintptr_t)_attribute[field].prolongation-(uintptr_t)main) : 0ULL);
  for(int b=0;b<nboundary;b++)fprintf(aux_metadata,"%s%llu",b?",":"",_attribute[field].boundary[b] ? (unsigned long long)((uintptr_t)_attribute[field].boundary[b]-(uintptr_t)main) : 0ULL);
  fputs("]}\n",aux_metadata);
}
static double *aux_operand_access(double *ptr,int site,int role,int kind,int level,int i,int j,int k,int field,int di,int dj,int dk) {
  if(!aux_active)return ptr;
  aux_field(field);
  AuxOperandRecord r={.site=site,.role=role,.kind=kind,.level=level,.i=i,.j=j,.k=k,.field=field,.di=di,.dj=dj,.dk=dk,.bc=_attribute[field].stencil.bc};
  /* No floating computation and no read of write-only or escaped storage. */
  if(role==1 || role==3){memcpy(&r.value,ptr,sizeof(double));aux_reads++;}
  if(role==2 || role==3)aux_writes++;
  if(role==4)aux_escapes++;
  aux_emit(r);
  return ptr;
}
static void aux_operand_event(int site,int first,int second,double value) {
  if(!aux_active)return;
  AuxOperandRecord r={.site=site,.role=0,.level=first,.i=second,.value=value};aux_emit(r);
}
static int *aux_metadata_access(int *ptr,int site,int role,int field,int member) {
  if(!aux_active)return ptr;
  if(role==1 || role==3)aux_field(field);
  AuxOperandRecord r={.site=site,.role=role,.kind=3,.level=-1,.field=field,.di=member};
  if(role==1 || role==3){r.value=*ptr;aux_reads++;}
  if(role==2 || role==3)aux_writes++;
  if(role==4)aux_escapes++;
  aux_emit(r);return ptr;
}
static double *aux_constant_access(double *ptr,int site,int role,int index) {
  if(!aux_active)return ptr;
  AuxOperandRecord r={.site=site,.role=role,.kind=4,.level=-1,.field=index};
  if(role==1 || role==3){memcpy(&r.value,ptr,sizeof(double));aux_reads++;}
  if(role==2 || role==3)aux_writes++;
  if(role==4)aux_escapes++;
  aux_emit(r);return ptr;
}
static int aux_topology_predicate(int value,int site,int level,int i,int j,int k) {
  if(aux_active){
    AuxOperandRecord r={.site=site,.role=1,.kind=5,.level=level,.i=i,.j=j,.k=k,.field=-1,.value=value};
    aux_reads++;aux_emit(r);
  }
  return value;
}
static void aux_operand_begin(int pressure,double step,int relaxation) {
  if(enable_forensic_probes!=2)return;
  if(aux_active)aux_fail("nested_projection");
  if(iter!=363 || strcmp(_attribute[pressure].name,"pf"))return;
  if(aux_completed)aux_fail("duplicate_projection_window");
  scalar ps={pressure};
  if(!projection_trace_active(ps))aux_fail("outside_declared_forensic_window");
  if(sizeof(double)!=8 || sizeof(int32_t)!=4)aux_fail("unsupported_numeric_layout");
  unsigned one=1;if(*(unsigned char*)&one!=1)aux_fail("unsupported_endianness");
  char path[1200];
  if(snprintf(path,sizeof(path),"%s/aux-operand-values.bin.gz",output_dir)>=(int)sizeof(path))aux_fail("path_overflow");
  aux_fd=open(path,O_WRONLY|O_CREAT|O_EXCL,0600);if(aux_fd<0)aux_fail("exclusive_trace_create");
  aux_stream=gzdopen(aux_fd,"wb1");if(!aux_stream || gzbuffer(aux_stream,65536))aux_fail("gzip_open");
  snprintf(path,sizeof(path),"%s/aux-operand-metadata.jsonl",output_dir);
  aux_metadata=fopen(path,"wx");if(!aux_metadata)aux_fail("exclusive_metadata_create");
  fprintf(aux_metadata,"{\"schema\":\"aux_consumed_operands_v1\",\"iteration\":%d,\"time\":%.17g,\"dt\":%.17g,\"pressure\":%d,\"nrelax\":%d,\"record_bytes\":64,\"endianness\":\"little\",\"site_manifest_required\":true,\"bulk_snapshot_dependency\":false}\n",iter,t,step,pressure,relaxation);
  aux_active=1;
  /* Entry metadata is separately labelled, not evidence of a numerical read. */
  aux_field(pressure);
  aux_operand_event(-10,iter,relaxation,step);
}
static void aux_operand_end(void) {
  if(!aux_active)return;
  aux_operand_event(-11,iter,0,t);aux_flush();
  if(gzflush(aux_stream,Z_FINISH)!=Z_OK || fsync(aux_fd))aux_fail("gzip_sync");
  if(gzclose(aux_stream)!=Z_OK)aux_fail("gzip_close");
  fprintf(aux_metadata,"{\"event\":\"terminal\",\"records\":%llu,\"reads\":%llu,\"writes\":%llu,\"address_escapes\":%llu,\"complete\":true}\n",(unsigned long long)aux_count,(unsigned long long)aux_reads,(unsigned long long)aux_writes,(unsigned long long)aux_escapes);
  fflush(aux_metadata);fsync(fileno(aux_metadata));fclose(aux_metadata);
  aux_active=0;aux_completed=1;
}
