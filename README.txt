README.txt
===========

Instruções para correr o projeto
--------------------------------

1. Pré-requisitos
   - Certifique-se de que tem Python 3 instalado.
   - Instale todas as dependências do projeto com:
     ```
     pip install -r requirements.txt
     ```
   - Se estiver a usar um ambiente virtual que já contém as dependências, certifique-se de ativá-lo:
     - Linux/MacOS: source <nome_do_env>/bin/activate
     
     - Windows: <nome_do_env>\Scripts\activate
     
     - Anaconda: conda activate <nome_do_env>

2. Preparação
   - Antes de correr o código, execute no terminal:
     ```
     spade run
     ```

3. Executar a interface
   - Para iniciar a interface, use:
     ```
     python3 interface.py
     ```
   - Será apresentada a opção de escolher entre:
     1. **Manual**
     2. **Layout**

4. Modo Manual
   - Existem 2 configurações de ambiente disponíveis.
   - Todos os elementos extras (bins, trucks, roadblocks e trânsito) devem ser adicionados manualmente.
   - Use os comandos disponíveis no menu do lado direito para configurar cada elemento.

5. Modo Layout
   - Existem 5 configurações pré-definidas guardadas na pasta `configs`:
     ```
     configs/config1.json
     configs/config2.json
     configs/config3.json
     configs/config4.json
     configs/config5.json
     ```
   - Após escolher **Layout**, deve indicar o caminho para uma das configurações, por exemplo:
     ```
     configs/config3.json
     ```
   - Estas configurações já incluem roadblocks, trânsito e os dois tipos de agentes.

6. Iniciar o sistema
   - Para iniciar o sistema após carregar a configuração escolhida, clique em **Start** na interface.

Observações
-----------
- Certifique-se de que todos os comandos são introduzidos corretamente conforme aparecem na interface.
- Para qualquer problema de dependências ou execução, verifique se o ambiente virtual está ativado corretamente.

Nota extra:
- Na pasta "documented" tem o código documentado. A partir de index.html consegue aceder aos 4 ficheiros documentados desenvolvidos durante o projeto (bin_agent, truck_agent, environment e interface).
