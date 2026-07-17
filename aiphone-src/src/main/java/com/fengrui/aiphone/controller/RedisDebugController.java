package com.fengrui.aiphone.controller;

import com.fengrui.aiphone.common.Result;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.redis.connection.DataType;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.web.bind.annotation.*;

import java.util.*;

/**
 * Redis 调试 Controller（仅开发测试用，生产环境应禁用或加权限校验）。
 * <p>用于查看 Redis 中的缓存内容，验证缓存策略。</p>
 */
@RestController
@RequestMapping("/test/redis")
public class RedisDebugController {

    @Autowired
    private RedisTemplate<String, Object> redisTemplate;

    /**
     * 列出所有 key（按 pattern 匹配）。
     * <p>用法：GET /test/redis/keys?pattern=dialogue:buffer:*</p>
     */
    @GetMapping("/keys")
    public Result<Map<String, Object>> keys(@RequestParam(defaultValue = "*") String pattern) {
        Set<String> keys = redisTemplate.keys(pattern);
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("pattern", pattern);
        data.put("count", keys != null ? keys.size() : 0);
        data.put("keys", keys);
        return Result.success(data);
    }

    /**
     * 查看指定 key 的详情（自动识别类型）。
     * <p>用法：GET /test/redis/get?key=dialogue:buffer:17</p>
     */
    @GetMapping("/get")
    public Result<Map<String, Object>> get(@RequestParam String key) {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("key", key);
        DataType type = redisTemplate.type(key);
        data.put("type", type.code());

        switch (type) {
            case STRING:
                data.put("value", redisTemplate.opsForValue().get(key));
                break;
            case LIST:
                data.put("size", redisTemplate.opsForList().size(key));
                data.put("values", redisTemplate.opsForList().range(key, 0, -1));
                break;
            case HASH:
                data.put("entries", redisTemplate.opsForHash().entries(key));
                break;
            case SET:
                data.put("members", redisTemplate.opsForSet().members(key));
                break;
            case ZSET:
                data.put("values", redisTemplate.opsForZSet().rangeWithScores(key, 0, -1));
                break;
            case NONE:
                data.put("value", "(key 不存在)");
                break;
        }

        Long ttl = redisTemplate.getExpire(key);
        data.put("ttl_seconds", ttl);
        return Result.success(data);
    }

    /**
     * 删除指定 key。
     * <p>用法：DELETE /test/redis/del?key=dialogue:buffer:17</p>
     */
    @DeleteMapping("/del")
    public Result<Map<String, Object>> del(@RequestParam String key) {
        Boolean deleted = redisTemplate.delete(key);
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("key", key);
        data.put("deleted", deleted);
        return Result.success(data);
    }

    /**
     * 查看本项目的核心缓存概览（对话缓冲 + 前置状态 + 坐席状态）。
     * <p>用法：GET /test/redis/overview</p>
     */
    @GetMapping("/overview")
    public Result<Map<String, Object>> overview() {
        Map<String, Object> data = new LinkedHashMap<>();

        // 对话缓冲
        Set<String> dialogueKeys = redisTemplate.keys("dialogue:buffer:*");
        List<Map<String, Object>> dialogueList = new ArrayList<>();
        if (dialogueKeys != null) {
            for (String key : dialogueKeys) {
                Map<String, Object> entry = new LinkedHashMap<>();
                entry.put("key", key);
                entry.put("size", redisTemplate.opsForList().size(key));
                entry.put("ttl_seconds", redisTemplate.getExpire(key));
                dialogueList.add(entry);
            }
        }
        data.put("dialogue_buffers", dialogueList);

        // CCC 前置状态
        Set<String> metaKeys = redisTemplate.keys("ccc:contact:*:meta");
        List<Map<String, Object>> metaList = new ArrayList<>();
        if (metaKeys != null) {
            for (String key : metaKeys) {
                Map<String, Object> entry = new LinkedHashMap<>();
                entry.put("key", key);
                entry.put("entries", redisTemplate.opsForHash().entries(key));
                entry.put("ttl_seconds", redisTemplate.getExpire(key));
                metaList.add(entry);
            }
        }
        data.put("ccc_contact_meta", metaList);

        // 坐席状态
        Set<String> agentKeys = redisTemplate.keys("agent:status:*");
        List<Map<String, Object>> agentList = new ArrayList<>();
        if (agentKeys != null) {
            for (String key : agentKeys) {
                Map<String, Object> entry = new LinkedHashMap<>();
                entry.put("key", key);
                entry.put("value", redisTemplate.opsForValue().get(key));
                entry.put("ttl_seconds", redisTemplate.getExpire(key));
                agentList.add(entry);
            }
        }
        data.put("agent_status", agentList);

        data.put("total_keys", (dialogueKeys != null ? dialogueKeys.size() : 0)
                + (metaKeys != null ? metaKeys.size() : 0)
                + (agentKeys != null ? agentKeys.size() : 0));
        return Result.success(data);
    }
}
