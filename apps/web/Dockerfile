FROM node:24-alpine AS build

WORKDIR /app
ARG VITE_PORTAL=student
ARG VITE_STUDENT_ORIGIN
ARG VITE_TEACHER_ORIGIN
ENV VITE_PORTAL=${VITE_PORTAL}
ENV VITE_STUDENT_ORIGIN=${VITE_STUDENT_ORIGIN}
ENV VITE_TEACHER_ORIGIN=${VITE_TEACHER_ORIGIN}
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:1.29-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
