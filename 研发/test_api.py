#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试脚本 - 验证所有API接口"""
import requests
import time
import sys

BASE_URL = "http://localhost:8080/api"

def test_health():
    """测试健康检查接口"""
    print("\n=== 1. 测试健康检查接口 ===")
    try:
        res = requests.get(f"{BASE_URL}/health")
        print(f"状态码: {res.status_code}")
        print(f"响应: {res.text}")
        return res.status_code == 200
    except Exception as e:
        print(f"失败: {e}")
        return False

def test_login(username="test_user"):
    """测试登录接口"""
    print("\n=== 2. 测试登录接口 ===")
    try:
        res = requests.post(
            f"{BASE_URL}/auth/login",
            json={"username": username, "password": "test123"}
        )
        print(f"状态码: {res.status_code}")
        print(f"响应: {res.text}")
        return res.status_code == 200
    except Exception as e:
        print(f"失败: {e}")
        return False

def test_roles():
    """测试角色列表接口"""
    print("\n=== 3. 测试角色列表接口 ===")
    try:
        res = requests.get(f"{BASE_URL}/roles")
        print(f"状态码: {res.status_code}")
        print(f"响应: {res.text}")
        if res.status_code == 200:
            data = res.json()
            print(f"角色数量: {len(data)}")
            return True
    except Exception as e:
        print(f"失败: {e}")
        return False
    return False

def test_chat():
    """测试聊天接口"""
    print("\n=== 4. 测试聊天接口 ===")
    try:
        res = requests.post(
            f"{BASE_URL}/chat",
            json={
                "user_id": "test_user",
                "role_code": "doctor",
                "message": "你好",
                "session_id": "default"
            }
        )
        print(f"状态码: {res.status_code}")
        print(f"响应: {res.text}")
        if res.status_code == 200:
            data = res.json()
            print(f"success: {data.get('success')}")
            print(f"response: {data.get('response', '')[:100]}...")
            return True
    except Exception as e:
        print(f"失败: {e}")
        return False
    return False

def test_sessions():
    """测试会话列表接口"""
    print("\n=== 5. 测试会话列表接口 ===")
    try:
        res = requests.get(f"{BASE_URL}/sessions?user_id=test_user&role_code=doctor")
        print(f"状态码: {res.status_code}")
        print(f"响应: {res.text}")
        return res.status_code == 200
    except Exception as e:
        print(f"失败: {e}")
        return False

def main():
    print("=" * 50)
    print("开始API测试")
    print("=" * 50)
    
    results = []
    
    # 等待服务启动
    print("\n等待服务启动...")
    time.sleep(2)
    
    # 测试1: 健康检查
    results.append(("健康检查", test_health()))
    
    # 测试2: 登录
    results.append(("登录", test_login()))
    
    # 测试3: 角色列表
    results.append(("角色列表", test_roles()))
    
    # 测试4: 聊天
    results.append(("聊天", test_chat()))
    
    # 测试5: 会话列表
    results.append(("会话列表", test_sessions()))
    
    # 总结
    print("\n" + "=" * 50)
    print("测试总结:")
    print("=" * 50)
    all_passed = True
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{name}: {status}")
        if not passed:
            all_passed = False
    
    print("\n" + "=" * 50)
    if all_passed:
        print("🎉 所有测试通过！")
        return 0
    else:
        print("❌ 部分测试失败，请检查")
        return 1

if __name__ == "__main__":
    sys.exit(main())