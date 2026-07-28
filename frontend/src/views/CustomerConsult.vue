<template>
  <main class="consult-shell">
    <header class="consult-header">
      <div class="wordmark"><span>EA</span><div><b>商品咨询</b><small>依据已审核商品事实回答</small></div></div>
      <div class="privacy-note">本地 Demo · 匿名会话 · 不需要后台账号</div>
    </header>
    <section class="consult-layout">
      <aside class="product-card">
        <div class="eyebrow">咨询对象</div><h1>{{ selectedProduct?.name || "选择商品后开始咨询" }}</h1>
        <p>{{ selectedProduct?.summary || "这里只展示已批准、可面向顾客的商品事实。" }}</p>
        <el-select v-model="productId" placeholder="请选择商品" :disabled="Boolean(conversationId)" class="product-select">
          <el-option v-for="product in products" :key="product.id" :label="product.name" :value="product.id" />
        </el-select>
        <div class="fact-stamp"><span>事实范围</span><b>已批准商品 · SKU 规格 · 已审核 FAQ</b></div>
        <p class="boundary">价格、优惠、物流承诺、退款售后、功效争议等问题将由人工客服处理。</p>
      </aside>
      <section class="conversation-card">
        <div class="conversation-head"><div><span class="overline">PRE-SALE SERVICE</span><h2>售前咨询</h2></div><span class="status-chip" :class="conversation?.status || 'new'">{{ statusLabel }}</span></div>
        <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
        <div v-if="!conversationId" class="conversation-empty">
          <div class="empty-mark">?</div><h3>从一个具体商品开始</h3><p>创建匿名会话后，系统只会使用已批准且可追溯的商品事实。</p>
          <el-button type="primary" :loading="loading" :disabled="!productId" @click="start">开始咨询</el-button>
        </div>
        <template v-else>
          <div class="state-notice" :class="conversation?.status" v-if="customerNotice"><strong>{{ customerNotice.title }}</strong><span>{{ customerNotice.detail }}</span></div>
          <div ref="timeline" class="message-list" aria-live="polite">
            <div v-if="!conversation?.messages.length" class="message-placeholder">请描述你想了解的商品信息。</div>
            <article v-for="message in conversation?.messages" :key="message.id" class="message" :class="message.sender_type">
              <small>{{ senderLabel(message.sender_type) }}</small><p>{{ message.content }}</p><time>{{ formatTime(message.created_at) }}</time>
            </article>
          </div>
          <form class="composer" @submit.prevent="send">
            <el-input v-model="question" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" maxlength="500" show-word-limit placeholder="例如：这款商品的材质是什么？" :disabled="!canCustomerSend(conversation?.status)" />
            <el-button type="primary" native-type="submit" :loading="sending" :disabled="!question.trim() || !canCustomerSend(conversation?.status)">发送问题</el-button>
          </form>
        </template>
      </section>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from "vue";
import { errorMessage } from "../api/client";
import { canCustomerSend, customerStatusText, isUncertainTransferReason, m3Api, type ConversationMessage, type CustomerConversation, type CustomerProduct } from "../api/milestone3";
const storageKey = "ecomagent_customer_conversation";
const products=ref<CustomerProduct[]>([]),productId=ref<number>(),conversationId=ref<number|string>(),accessToken=ref(""),conversation=ref<CustomerConversation>(),question=ref(""),loading=ref(false),sending=ref(false),error=ref(""),timeline=ref<HTMLElement>();
const selectedProduct=computed(()=>products.value.find(item=>item.id===productId.value));
const statusLabel=computed(()=>customerStatusText(conversation.value?.status));
const customerNotice=computed(()=>conversation.value?.status==="transferred"?{title:isUncertainTransferReason(conversation.value.reason_code)?"当前信息无法确认，已转人工":"已转人工，请等待客服处理",detail:"我们不会承诺具体响应时间，请稍后刷新查看。"}:conversation.value?.notice?{title:"暂时无法确认",detail:conversation.value.notice}:conversation.value?.status==="waiting_review"?{title:"正在等待客服审核",detail:"该问题不会自动回复，客服确认后会在这里发送答复。"}:undefined);
function senderLabel(sender:ConversationMessage["sender_type"]){return ({customer:"我",assistant:"事实助手",customer_service:"人工客服",system:"系统状态"})[sender]}
function formatTime(value:string){const date=new Date(value);return !value||Number.isNaN(date.getTime())?value:date.toLocaleTimeString("zh-CN",{hour:"2-digit",minute:"2-digit"})}
function persist(){sessionStorage.setItem(storageKey,JSON.stringify({conversationId:conversationId.value,accessToken:accessToken.value,productId:productId.value}))}
async function scrollLatest(){await nextTick();timeline.value?.scrollTo({top:timeline.value.scrollHeight,behavior:"smooth"})}
async function start(){if(!productId.value)return;loading.value=true;error.value="";try{const created=await m3Api.createConversation(productId.value);conversationId.value=created.id;accessToken.value=created.access_token;conversation.value=created;persist()}catch(e){error.value=errorMessage(e)}finally{loading.value=false}}
async function send(){if(!conversationId.value||!accessToken.value||!question.value.trim()||!canCustomerSend(conversation.value?.status))return;sending.value=true;error.value="";try{conversation.value=await m3Api.sendCustomerMessage(conversationId.value,accessToken.value,question.value.trim());question.value="";await scrollLatest()}catch(e){error.value=errorMessage(e)}finally{sending.value=false}}
async function restore(){const saved=sessionStorage.getItem(storageKey);if(!saved)return;try{const parsed=JSON.parse(saved) as {conversationId?:number|string;accessToken?:string;productId?:number};if(!parsed.conversationId||!parsed.accessToken)return;conversationId.value=parsed.conversationId;accessToken.value=parsed.accessToken;productId.value=parsed.productId;conversation.value=await m3Api.getCustomerConversation(parsed.conversationId,parsed.accessToken)}catch{sessionStorage.removeItem(storageKey);conversationId.value=undefined;accessToken.value="";error.value="当前会话凭据已失效，请重新创建咨询。"}}
onMounted(async()=>{loading.value=true;try{products.value=await m3Api.listCustomerProducts();if(!productId.value)productId.value=products.value[0]?.id;await restore()}catch(e){error.value=errorMessage(e)}finally{loading.value=false}});
</script>

<style scoped>
.consult-shell{min-height:100vh;background:#eef2ed;color:#163129;padding:0 28px 44px;background-image:linear-gradient(90deg,#173b2f0a 1px,transparent 1px),linear-gradient(#173b2f0a 1px,transparent 1px);background-size:32px 32px}.consult-header{height:86px;max-width:1180px;margin:auto;display:flex;align-items:center;justify-content:space-between}.wordmark{display:flex;align-items:center;gap:12px}.wordmark>span{display:grid;place-items:center;width:42px;height:42px;background:#173b2f;color:#edf7f1;font-family:Georgia,serif;font-weight:700}.wordmark b,.wordmark small{display:block}.wordmark b{font-size:17px}.wordmark small,.privacy-note{font-size:12px;color:#65776f;margin-top:3px}.consult-layout{max-width:1180px;margin:24px auto 0;display:grid;grid-template-columns:330px minmax(0,1fr);gap:22px}.product-card,.conversation-card{background:#fff;border:1px solid #d6e0da;box-shadow:0 20px 60px #18382c12}.product-card{align-self:start;padding:30px;position:relative;overflow:hidden}.product-card:before{content:"";position:absolute;right:-42px;top:-42px;width:116px;height:116px;border:18px solid #dceae2;border-radius:50%}.product-card h1{font-size:25px;line-height:1.35;margin:18px 0 8px;max-width:240px}.product-card>p{color:#66766f;line-height:1.7}.product-select{width:100%;margin:14px 0}.fact-stamp{margin-top:14px;padding:12px 14px;border-left:3px solid #148167;background:#f0f6f2;display:grid;gap:4px}.fact-stamp span{font-size:11px;color:#6a7a73;letter-spacing:.1em}.fact-stamp b{font-size:12px}.product-card .boundary{border-top:1px solid #e1e8e3;margin:22px 0 0;padding-top:18px;font-size:12px}.conversation-card{min-height:650px;display:flex;flex-direction:column}.conversation-head{padding:24px 28px;border-bottom:1px solid #dce4df;display:flex;align-items:center;justify-content:space-between}.conversation-head h2{margin:3px 0 0;font-size:21px}.overline{font:11px/1.2 Georgia,serif;letter-spacing:.14em;color:#148167}.status-chip{font-size:12px;padding:7px 10px;border:1px solid #ccd8d2;background:#f5f8f6}.status-chip.waiting_review{color:#8d5d00;background:#fff7e4;border-color:#ebd39c}.status-chip.transferred{color:#8c3d32;background:#fff0ed;border-color:#edc6bf}.status-chip.resolved{color:#66766f;background:#edf1ee}.conversation-card>:deep(.el-alert){margin:16px 28px 0;width:auto}.conversation-empty{margin:auto;text-align:center;max-width:410px;padding:60px 24px}.empty-mark{width:56px;height:56px;border:1px solid #9eb4aa;margin:0 auto 20px;display:grid;place-items:center;font:italic 28px Georgia,serif;color:#0f775c}.conversation-empty h3{margin:0 0 8px}.conversation-empty p{color:#687770;line-height:1.7;margin:0 0 24px}.state-notice{margin:16px 28px 0;padding:12px 14px;background:#fff8e8;border-left:3px solid #cc941f;display:grid;gap:4px}.state-notice.transferred{background:#fff1ee;border-color:#b85447}.state-notice span{font-size:12px;color:#687770}.message-list{height:420px;overflow:auto;padding:24px 28px;display:flex;flex-direction:column;gap:16px}.message-placeholder{margin:auto;color:#829089;font-size:13px}.message{max-width:78%;padding:12px 15px;border:1px solid #dae3de;background:#f5f8f6;align-self:flex-start}.message.customer{align-self:flex-end;background:#173b2f;color:#f5fbf7;border-color:#173b2f}.message small{font-size:11px;opacity:.72}.message p{margin:5px 0 6px;white-space:pre-wrap;line-height:1.65}.message time{display:block;font-size:10px;opacity:.6;text-align:right}.composer{margin-top:auto;border-top:1px solid #dce4df;padding:18px 28px;display:grid;grid-template-columns:1fr auto;gap:12px;align-items:end}@media(max-width:800px){.consult-shell{padding:0 14px 22px}.consult-header{height:72px}.privacy-note{display:none}.consult-layout{margin-top:10px;grid-template-columns:1fr}.product-card{padding:20px}.product-card:before{display:none}.product-card h1{font-size:20px}.conversation-card{min-height:620px}.conversation-head,.message-list{padding-left:18px;padding-right:18px}.state-notice{margin-left:18px;margin-right:18px}.composer{padding:14px 18px;grid-template-columns:1fr}.composer .el-button{width:100%}.message{max-width:88%}}
</style>
