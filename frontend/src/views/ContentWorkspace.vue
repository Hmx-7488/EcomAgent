<template>
  <section>
    <div class="page-heading"><div><div class="eyebrow">事实优先 / Content package</div><h1>内容素材工作台</h1><p>每个内容包绑定已批准商品事实版本；批准版本只读，导出仅在批准后开放。</p></div><div class="heading-actions"><el-select v-model="selectedProductId" placeholder="选择已批准商品" filterable :loading="productLoading" :disabled="productLoading || productOptions.length === 0"><el-option v-for="product in productOptions" :key="product.id" :label="product.name" :value="product.id" /></el-select><el-button type="primary" :disabled="!selectedProductId || productLoading" :loading="working" @click="create">新建内容包</el-button></div></div>
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon class="notice" />
    <el-alert v-else-if="!productLoading && productOptions.length === 0" type="warning" title="暂无可用于内容包的已批准商品。" :closable="false" show-icon class="notice" />
    <div class="layout">
      <aside class="package-list panel" v-loading="loading"><div class="list-label">内容包 / {{ packages.length }}</div><button v-for="item in packages" :key="item.id" class="package-row" :class="{active:selected?.id===item.id}" @click="selected=item"><span>{{ productName(item.product_id) }}</span><small>v{{ item.version }} · {{ statusText(item.status) }}</small></button></aside>
      <main v-if="selected" class="content-detail">
        <div class="fact-strip"><div><span>事实来源</span><b>{{ selected.fact_version }}</b><p>{{ selected.input_summary }}</p></div><div><span>生成记录</span><b>{{ selected.provider || '—' }} / {{ selected.model_name || '—' }}</b><p>{{ selected.task_status || '未生成' }}{{ selected.error_summary ? ` · ${selected.error_summary}` : '' }}</p></div><el-tag :type="tagType(selected.status)">{{ statusText(selected.status) }}</el-tag></div>
        <div class="panel editor"><div class="editor-head"><div><b>内容版本 v{{ selected.version }}</b><small>最后更新 {{ selected.updated_at }}</small></div><div class="actions"><el-button :loading="working" @click="generate" :disabled="selected.status==='approved'">生成</el-button><el-button v-if="selected.status==='draft'||selected.status==='rejected'" type="primary" @click="act('submit')">提交审批</el-button><el-button v-if="selected.status==='approved'" type="success" @click="act('export')">导出 Markdown</el-button></div></div>
          <el-alert v-if="selected.status==='approved'" title="已批准版本不可编辑；如需修改，请新建内容包版本。" type="success" :closable="false" />
          <el-alert v-else-if="selected.status==='rejected'" :title="`已拒绝：${selected.rejection_reason || '未记录原因'}`" type="error" :closable="false" />
          <el-tabs v-model="tab" class="content-tabs"><el-tab-pane v-for="field in fields" :key="field.key" :label="field.label" :name="field.key"><el-input v-model="draft[field.key]" type="textarea" :autosize="{minRows:6,maxRows:12}" :disabled="selected.status==='approved'||saving" @blur="save" /></el-tab-pane></el-tabs>
          <div class="version-note"><b>版本对比</b><span>当前版本以 {{ selected.fact_version }} 为输入快照；历史已批准版本不会被覆盖。</span></div>
        </div>
      </main>
      <main v-else class="panel empty">请选择一个内容包。</main>
    </div>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { errorMessage } from "../api/client";
import { contentGenerationError, m2Api, type ApprovalStatus, type ContentPackage, type ProductOption } from "../api/milestone2";
const packages=ref<ContentPackage[]>([]), selected=ref<ContentPackage>(), productOptions=ref<ProductOption[]>([]), selectedProductId=ref<number>(), loading=ref(false), productLoading=ref(false), working=ref(false), error=ref(""), tab=ref("title");
const fields = [{key:"title",label:"标题"},{key:"selling_points",label:"卖点"},{key:"detail",label:"详情"},{key:"parameters",label:"参数说明"},{key:"faq",label:"FAQ"},{key:"presale_script",label:"售前话术"},{key:"promotion_material",label:"图文推广素材"}] as const;
type ContentFieldKey = (typeof fields)[number]["key"];
type ContentSnapshot = Record<ContentFieldKey, string>;
function emptySnapshot():ContentSnapshot{return {title:"",selling_points:"",detail:"",parameters:"",faq:"",presale_script:"",promotion_material:""}}
function snapshotFrom(source?:Partial<Record<ContentFieldKey,unknown>>):ContentSnapshot{const snapshot=emptySnapshot();fields.forEach(field=>{const value=source?.[field.key];snapshot[field.key]=typeof value==="string"?value:""});return snapshot}
function snapshotsEqual(left:ContentSnapshot,right:ContentSnapshot){return fields.every(field=>left[field.key]===right[field.key])}
const draft = reactive<ContentSnapshot>(emptySnapshot()), saving=ref(false);
let persistedSnapshot=emptySnapshot();
function loadDraft(item?: ContentPackage){const snapshot=snapshotFrom(item);fields.forEach(field=>draft[field.key]=snapshot[field.key]);persistedSnapshot=snapshot}
watch(selected, loadDraft, {immediate:true});
function statusText(status:ApprovalStatus){return ({draft:"草稿",submitted:"待审批",approved:"已批准",rejected:"已拒绝"})[status]}
function tagType(status:ApprovalStatus){return ({draft:"info",submitted:"warning",approved:"success",rejected:"danger"})[status] as "info"|"warning"|"success"|"danger"}
const productNames=computed(()=>new Map(productOptions.value.map(product=>[product.id,product.name])));
function productName(productId:number){return productNames.value.get(productId)||`商品 #${productId}`}
async function loadProducts(){productLoading.value=true;error.value="";try{productOptions.value=await m2Api.listApprovedProducts()}catch(e){error.value=errorMessage(e)}finally{productLoading.value=false}}
async function refresh(){loading.value=true;try{const selectedId=selected.value?.id;packages.value=await m2Api.listPackages();selected.value=packages.value.find(item=>item.id===selectedId)||packages.value[0]}catch(e){error.value=errorMessage(e)}finally{loading.value=false}}
async function create(){if(!selectedProductId.value)return;working.value=true;error.value="";try{const item=await m2Api.createPackage(selectedProductId.value);await refresh();selected.value=packages.value.find(p=>p.id===item.id);ElMessage.success("已创建内容包草稿")}catch(e){error.value=errorMessage(e)}finally{working.value=false}}
async function save(){const item=selected.value;if(!item||item.status==="approved"||saving.value)return;const requestSnapshot=snapshotFrom(draft);if(snapshotsEqual(requestSnapshot,persistedSnapshot))return;saving.value=true;error.value="";try{const updated=await m2Api.updatePackage(item.id,requestSnapshot);replace(updated)}catch(e){error.value=errorMessage(e)}finally{saving.value=false}}
function replace(item:ContentPackage){packages.value=packages.value.map(p=>p.id===item.id?item:p);selected.value=item;loadDraft(item)}
async function generate(){if(!selected.value)return;working.value=true;error.value="";try{const generated=await m2Api.generatePackage(selected.value.id);replace(generated);const generationError=contentGenerationError(generated);if(generationError){error.value=generationError;return}ElMessage.success("内容生成任务已完成")}catch(e){error.value=errorMessage(e)}finally{working.value=false}}
async function act(action:"submit"|"export"){if(!selected.value)return;working.value=true;try{replace(await m2Api.packageAction(selected.value.id,action));ElMessage.success(action==="export"?"已导出 Markdown 并记录审计":"已提交管理员审批")}catch(e){error.value=errorMessage(e)}finally{working.value=false}}
onMounted(()=>Promise.all([loadProducts(),refresh()]));
</script>
<style scoped>
.heading-actions{display:flex;gap:10px;align-items:center}.heading-actions :deep(.el-select){width:240px}.layout{display:grid;grid-template-columns:255px minmax(0,1fr);gap:18px}.package-list{padding:10px;height:max-content}.list-label{padding:8px 10px;color:var(--muted);font-size:12px}.package-row{display:grid;gap:4px;width:100%;text-align:left;padding:12px 10px;border:0;border-left:3px solid transparent;background:transparent;cursor:pointer;color:var(--ink)}.package-row:hover,.package-row.active{background:#eff6f2;border-left-color:var(--green)}.package-row small,.editor-head small{color:var(--muted)}.fact-strip{display:grid;grid-template-columns:1fr 1fr auto;gap:20px;padding:15px 18px;margin-bottom:14px;background:var(--warm);border:1px solid #e8dfcf;border-radius:7px}.fact-strip span{display:block;font-size:12px;color:var(--muted);margin-bottom:4px}.fact-strip b{font-size:14px}.fact-strip p{margin:4px 0 0;font-size:12px;color:var(--muted)}.editor-head{display:flex;justify-content:space-between;gap:14px}.editor-head small{display:block;margin-top:4px}.notice{margin-bottom:14px}.content-tabs{margin-top:8px}.version-note{display:grid;gap:5px;padding:12px 14px;background:#f7f9f7;border-left:3px solid #87aa9c;font-size:13px;color:var(--muted)}.version-note b{color:var(--ink)}.empty{color:var(--muted)}@media(max-width:850px){.heading-actions{display:grid}.layout{grid-template-columns:1fr}.fact-strip{grid-template-columns:1fr}.editor-head{display:grid}}
</style>
