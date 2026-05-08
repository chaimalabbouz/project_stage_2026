les commandes pour faire l execution au debut : source venv/bin/activate           ///python -m extractor.image_downloader

!!!!!!!!!!!!!!!!!!!!!!
aujourd hui je dois faire ceci :
1)ameliorer la partie de l extraction de composantes reu , normal , t architecture 
2)on doit executer le projet 
3)je dois genrer le code 
4)voir le resulta de l execution 



https://www.figma.com/design/dBXu8H2arxIRSFGD65utb6/Banquee---SaaS---Bank-Website---Webflow-Template--Community-?node-id=0-1&p=f&t=aTBLBBLRA0fWdiR1-0    
--------------------------------------------------------------------------------------------------------
----------------------------------------------------------------------------------------------------------
readme pour la partie des composnat reutilisable
-"kind": "variant_set" : C'est l'étiquette que ton script Python a collée. Elle dit au LLM : "Attention, ce n'est pas un bloc unique, c'est une famille de composants qui partagent la même base mais ont des petites différences".
-"component_set_id": "23:1616" : C'est l'ID du "père" dans Figma (le COMPONENT_SET). Il sert de point de repère unique pour toute cette famille.
-"props_from_figma": {...} : C'est la partie la plus importante pour le LLM ! C'est le "mode d'emploi" du composant. Il dit au LLM : "Quand tu vas écrire le code React de ce composant, tu devras créer une variable (prop) qui s'appelle 'Size', de type 'VARIANT', et sa valeur par défaut devra être 'Small'".


##air llm , 



rm -rf data/planner/*
rm -rf data/component-reu/*














ceci est dans le prompt de llm generete code dans le fichier prompt jai enlver pour tester 
8. Add a JSX comment as the first child of every major block: {/* Figma ID: ... */}
















j'ai un projet ou je dois generer depuis un json figma d un design donné un project react , mais pour jai fait pour le moment plusieurs etapes comme par exemple recuperation de json le faire son cleaning extraction des comonent reutilisables leurs props .... , genere un un planing react du web site'extraire les pages ,section component possible et lordre de genetion , maintenant je suis dans l etpe la plus critique cesl la generation de code jai choisir 2 faire 2 agents 1 coder et un validator pour le moment je suis entrain de faire de faire la partir de coder , voici larchitecture que jai :codegen/
│
├── main.py
├── graph.py
├── state.py
│
├── agents/
│   ├── codegen_agent/
│   │   ├── agent.py
│   │   ├── prompt.txt
│   │   ├── tools.py
│   │   │
│   │   └── core/
│   │       ├── style_system.py
│   │       ├── asset_manager.py
│   │       ├── font_manager.py
│   │       └── route_manager.py
│   │
│   └── validation_agent/
│       ├── agent.py
│       ├── prompt.txt
│       ├── tools.py
│       └── fixer.py que ce que vouq trouver 











pour le moment je veux focuser sur ces fichiers ├── style_system.py font_manager.py pour avoir une fidelité visuelle le max cest pour ca je dois faire une coversuinsion figma tailwindcss pour que lagent puet utiliser leurs de coadges 


























PROMPT_COMPONENT = """
Tu es un expert React JSX. Tu reçois le JSON d'un composant avec ses classes Tailwind DÉJÀ CALCULÉES.
Règles STRICTES :
- Génère UNIQUEMENT le code JSX/React valide. Aucun texte, aucun markdown.
- Export par défaut : `export default function NomComposant() { ... }`
- Utilise exactement les "tailwind_classes" trouvées dans le JSON pour les className.
- Transforme les textes statiques ("characters") en variables/props logiques (ex: "banquee." -> prop title).
- Si l'élément est de type "IMAGE" ou un fond -> `<img src="/placeholder.jpg" alt="desc" className="[classes]" />`
"""













cd ~/projet_stage
 cd ~/projet_stage/data/generated_projects/fintech_landing
 npm run dev