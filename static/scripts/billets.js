document.addEventListener("DOMContentLoaded", function () {
  const epreuveSelect = document.getElementById("epreuve-select");

  // Ajout d'un écouteur pour détecter les changements de la sélection
  epreuveSelect.addEventListener("change", function () {
      const selectedValue = epreuveSelect.value;

      // Vérifie la sélection dans la console
      console.log('Épreuve sélectionnée :', selectedValue);

      // Si une option est sélectionnée (non vide)
      if (selectedValue) {
          // Sélectionne l'élément correspondant
          const billetItem = document.querySelector(selectedValue);
          console.log('Élément correspondant :', billetItem);

          // Si l'élément existe, on défile jusqu'à cet élément
          if (billetItem) {
              // Calcul du décalage pour centrer l'élément
              const offset = billetItem.getBoundingClientRect().top + window.scrollY - (window.innerHeight / 2) + (billetItem.clientHeight / 2);
              console.log('Offset calculé :', offset);

              window.scrollTo({
                  top: offset,  // Définit la position de défilement
                  behavior: 'smooth'  // Défilement en douceur
              });
              console.log('Défilement vers :', offset);
          } else {
              console.error('Élément introuvable pour :', selectedValue);  // Affiche une erreur si l'élément n'est pas trouvé
          }
      }
  });
});
