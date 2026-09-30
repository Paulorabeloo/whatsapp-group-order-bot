# Colocar o robô na nuvem (VPS)

Depois disso o robô roda 24h sem depender de computador ligado. Tempo total: uns 20 minutos.

## 1. Contratar a VPS

Qualquer VPS com **Ubuntu 24.04**, 1 vCPU, 1 a 2 GB de RAM, de preferência em São Paulo (IP brasileiro).
Exemplos: Hostinger VPS KVM 1, Contabo, Magalu Cloud. O robô usa menos de 300 MB de RAM.

Anote o **IP** e a **senha root** que o provedor mostra.

## 2. (Opcional) Apontar um subdomínio

No painel do domínio (ex.: `seudominio.com.br`), crie um registro **A**:

| Nome | Tipo | Valor |
|---|---|---|
| `robo` | A | IP da VPS |

Com isso o painel fica em `https://painel.seudominio.com.br`, com cadeado. Sem domínio, funciona em `http://IP:8080`.

## 3. Instalar (um comando)

Entre na VPS pelo terminal (no Windows: PowerShell):

```bash
ssh root@IP_DA_VPS
```

E rode (troque o domínio, ou tire o argumento se não tiver):

```bash
curl -fsSL https://raw.githubusercontent.com/Paulorabeloo/whatsapp-group-order-bot/main/deploy/install.sh | bash -s -- painel.seudominio.com.br
```

O script instala tudo, cria o serviço que reinicia sozinho, liga o backup diário, o firewall e o HTTPS.
No fim ele mostra a **senha do painel** (gerada na hora). Guarde.

## 4. Configurar

1. Abra o painel → **Conexão** → escaneie o QR com o celular do chip (WhatsApp → Aparelhos conectados).
2. Na mesma tela, clique em **Usar este** no grupo certo.
3. **Ajustes**: telefones dos admins, telefone que recebe os avisos, ritmo (fechar 60 min antes, contagem 30,5).
4. Modo **Sombra** por uma semana; depois **Ao vivo**.

> Se o robô já estava pareado no PC, dá pra pular o QR: copie `data/sessao.db` do PC pra `/opt/robo-grupo/data/`
> na VPS (e desligue o do PC, porque o WhatsApp só aceita uma sessão por vez).

## 5. Dia a dia

| Quero | Comando (na VPS, como root) |
|---|---|
| Ver o que o robô está fazendo | `journalctl -u robo-grupo -f` |
| Reiniciar | `systemctl restart robo-grupo` |
| Atualizar pra versão nova | `/opt/robo-grupo/deploy/update.sh` |
| Ver os backups | `ls /opt/robo-grupo/backups` |
| Restaurar um backup | `systemctl stop robo-grupo && tar -xzf /opt/robo-grupo/backups/AAAA-MM-DD.tar.gz -C /opt/robo-grupo && systemctl start robo-grupo` |
| Trocar a senha do painel | edite `PAINEL_SENHA` em `/opt/robo-grupo/.env` e reinicie |

## Se cair

- **Serviço caiu**: o systemd sobe de novo em 5 s, sozinho.
- **WhatsApp desconectou**: a biblioteca reconecta sozinha; se a sessão foi encerrada no celular, o painel volta a mostrar o QR.
- **Chip banido**: chip novo no grupo (admin, nunca dono), apague `data/sessao.db`, reinicie e escaneie o QR.
- **VPS sumiu**: nova VPS, mesmo comando de instalação, restaure o último backup.
