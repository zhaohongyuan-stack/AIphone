# 多阶段构建：第一阶段用 Maven 构建，第二阶段用 JRE 运行
# 优点：最终镜像不含 Maven/源码，体积小（约 200MB vs 800MB）

# ==================== 第一阶段：构建 ====================
FROM maven:3.9-eclipse-temurin-17 AS builder

WORKDIR /build

# 先复制 pom.xml 利用 Docker 缓存加速依赖下载
COPY pom.xml .
RUN mvn dependency:go-offline -B

# 复制源码并构建（跳过测试加速）
COPY src ./src
RUN mvn clean package -DskipTests -B

# ==================== 第二阶段：运行 ====================
FROM eclipse-temurin:17-jre

WORKDIR /app

# 复制构建产物
COPY --from=builder /build/target/*.jar app.jar

# 创建日志目录
RUN mkdir -p /app/logs

# 时区设置（中国时区）
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# JVM 参数（生产环境推荐）
# -Xms512m -Xmx512m：初始/最大堆内存（根据 ECS 配置调整）
# -XX:+UseG1GC：G1 垃圾回收器（适合服务端）
# -XX:+HeapDumpOnOutOfMemoryError：OOM 时自动 dump
ENV JAVA_OPTS="-Xms512m -Xmx512m -XX:+UseG1GC -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/app/logs/"

# 暴露应用端口
EXPOSE 8080

# 启动命令（通过 SPRING_PROFILES_ACTIVE 环境变量切换 profile，默认 docker）
ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -Dspring.profiles.active=${SPRING_PROFILES_ACTIVE:-docker} -jar app.jar"]
