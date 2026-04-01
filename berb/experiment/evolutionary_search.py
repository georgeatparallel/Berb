"""Evolutionary Experiment Search.

Based on AIRA2 (Meta FAIR) + Hive (arXiv:2603.26359):
"Maintain population of experiment variants, evolve toward better results."

Key Features:
- Population-based experiment search
- Temperature-scaled rank selection
- Mutation and crossover operations
- Multi-generation evolution
- HCE-guided selection

# Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    from berb.experiment.evolutionary_search import EvolutionaryExperimentSearch
    
    searcher = EvolutionaryExperimentSearch()
    result = await searcher.search(
        base_experiment=design,
        population_size=8,
        max_generations=4,
    )
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Any

from berb.reasoning.scientific import ExperimentDesign

logger = logging.getLogger(__name__)


@dataclass
class ExperimentVariant:
    """Variant of an experiment.
    
    Attributes:
        design: Experiment design
        fitness: Fitness score
        generation: Generation number
        parent_ids: Parent variant IDs
        mutations: Applied mutations
    """
    design: ExperimentDesign
    fitness: float = 0.0
    generation: int = 0
    parent_ids: list[str] = field(default_factory=list)
    mutations: list[str] = field(default_factory=list)
    
    @property
    def id(self) -> str:
        """Get variant ID."""
        return self.design.id


@dataclass
class EvolutionResult:
    """Result of evolutionary search.
    
    Attributes:
        best_variant: Best variant found
        generations: Number of generations
        population_history: Population history
        fitness_history: Fitness over generations
    """
    best_variant: ExperimentVariant
    generations: int
    population_history: list[list[ExperimentVariant]] = field(default_factory=list)
    fitness_history: list[float] = field(default_factory=list)


class EvolutionaryExperimentSearch:
    """AIRA2/Hive-inspired evolutionary experiment search.
    
    Features:
    - Population-based search over experiment variants
    - Temperature-scaled rank selection (AIRA2 Eq. 1)
    - Mutation and crossover operations
    - HCE-guided fitness evaluation
    - Parallel evaluation (uses AsyncExperimentPool)
    
    Usage:
        searcher = EvolutionaryExperimentSearch()
        result = await searcher.search(
            base_experiment=design,
            population_size=8,
            max_generations=4,
        )
    """
    
    def __init__(
        self,
        population_size: int = 8,
        max_generations: int = 4,
        mutation_rate: float = 0.3,
        crossover_rate: float = 0.5,
        temperature: float = 1.5,
    ):
        """Initialize evolutionary search.
        
        Args:
            population_size: Population size
            max_generations: Maximum generations
            mutation_rate: Probability of mutation
            crossover_rate: Probability of crossover
            temperature: Selection temperature (AIRA2 Eq. 1)
        """
        self.population_size = population_size
        self.max_generations = max_generations
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.temperature = temperature
        
        logger.info(
            f"Initialized EvolutionaryExperimentSearch "
            f"(pop={population_size}, gen={max_generations}, T={temperature})"
        )
    
    async def search(
        self,
        base_experiment: ExperimentDesign,
        fitness_fn: callable | None = None,
    ) -> EvolutionResult:
        """Run evolutionary search over experiment variants.
        
        Process:
        1. Create initial population of variants
        2. Run all variants (parallel via AsyncExperimentPool)
        3. Evaluate with fitness function (or HCE)
        4. Select best, mutate, crossover
        5. Repeat until convergence or max generations
        
        Args:
            base_experiment: Base experiment design
            fitness_fn: Fitness function (uses HCE if None)
            
        Returns:
            Evolution result
        """
        # Initialize population
        population = self._create_initial_population(base_experiment)
        
        population_history = []
        fitness_history = []
        best_variant = None
        best_fitness = float("-inf")
        
        for generation in range(self.max_generations):
            logger.info(f"Generation {generation + 1}/{self.max_generations}")
            
            # Evaluate population
            await self._evaluate_population(population, fitness_fn)
            
            # Track best
            for variant in population:
                if variant.fitness > best_fitness:
                    best_fitness = variant.fitness
                    best_variant = variant
            
            # Record history
            population_history.append(population.copy())
            fitness_history.append(best_fitness)
            
            # Check convergence
            if self._has_converged(population):
                logger.info(f"Converged at generation {generation + 1}")
                break
            
            # Create next generation
            population = self._create_next_generation(population, generation)
        
        return EvolutionResult(
            best_variant=best_variant or population[0],
            generations=len(fitness_history),
            population_history=population_history,
            fitness_history=fitness_history,
        )
    
    def _create_initial_population(
        self,
        base_experiment: ExperimentDesign,
    ) -> list[ExperimentVariant]:
        """Create initial population of variants.
        
        Args:
            base_experiment: Base experiment design
            
        Returns:
            Initial population
        """
        population = []
        
        for i in range(self.population_size):
            # Create variant with mutations
            variant_design = self._mutate_design(base_experiment, rate=0.5)
            variant_design.id = f"{base_experiment.id}_v{i}"
            
            variant = ExperimentVariant(
                design=variant_design,
                generation=0,
            )
            population.append(variant)
        
        logger.info(f"Created initial population of {len(population)} variants")
        return population
    
    def _mutate_design(
        self,
        design: ExperimentDesign,
        rate: float = 0.3,
    ) -> ExperimentDesign:
        """Mutate experiment design.
        
        Mutation types:
        - Parameter perturbation
        - Method variation
        - Constraint relaxation
        
        Args:
            design: Original design
            rate: Mutation rate
            
        Returns:
            Mutated design
        """
        import copy
        
        mutated = copy.deepcopy(design)
        mutations = []
        
        # Mutate methodology (if exists)
        if hasattr(mutated, 'methodology') and mutated.methodology:
            if random.random() < rate:
                # Add variation to methodology
                variations = [
                    " with increased sample size",
                    " with cross-validation",
                    " with ablation study",
                    " with sensitivity analysis",
                ]
                if isinstance(mutated.methodology, list):
                    idx = random.randint(0, len(mutated.methodology) - 1)
                    mutated.methodology[idx] += random.choice(variations)
                    mutations.append("methodology_variation")
        
        # Mutate variables (if exists)
        if hasattr(mutated, 'variables') and mutated.variables:
            if random.random() < rate:
                # Add control variable
                mutated.variables['controlled'] = mutated.variables.get('controlled', [])
                mutated.variables['controlled'].append(f"control_{random.randint(1, 100)}")
                mutations.append("variable_addition")
        
        return mutated
    
    async def _evaluate_population(
        self,
        population: list[ExperimentVariant],
        fitness_fn: callable | None = None,
    ) -> None:
        """Evaluate fitness of all variants.
        
        Args:
            population: Population to evaluate
            fitness_fn: Fitness function (uses HCE if None)
        """
        if fitness_fn is None:
            # Use HCE for evaluation
            from berb.validation.hidden_eval import HiddenConsistentEvaluation
            
            hce = HiddenConsistentEvaluation()
            
            for variant in population:
                # Create dummy paper for evaluation
                from berb.validation.hidden_eval import PaperDocument
                
                paper = PaperDocument(
                    id=variant.id,
                    title=f"Experiment: {variant.design.description}",
                    abstract=str(variant.design),
                    content=str(variant.design),
                )
                
                result = await hce.evaluate_for_search(paper)
                variant.fitness = result.overall_score
        else:
            # Use custom fitness function
            for variant in population:
                variant.fitness = await fitness_fn(variant)
        
        # Log fitness stats
        fitnesses = [v.fitness for v in population]
        logger.info(
            f"Population fitness: min={min(fitnesses):.2f}, "
            f"max={max(fitnesses):.2f}, mean={sum(fitnesses)/len(fitnesses):.2f}"
        )
    
    def _select_parent(
        self,
        population: list[ExperimentVariant],
    ) -> ExperimentVariant:
        """Select parent using temperature-scaled rank selection.
        
        AIRA2 Eq. 1: p(i) = (N - r_i + 1)^(1/T) / Σ(N - r_j + 1)^(1/T)
        
        Args:
            population: Current population
            
        Returns:
            Selected parent
        """
        # Sort by fitness (descending)
        sorted_pop = sorted(population, key=lambda v: v.fitness, reverse=True)
        n = len(sorted_pop)
        
        # Calculate rank probabilities
        probs = []
        for rank, variant in enumerate(sorted_pop):
            r = rank + 1  # 1-indexed rank
            score = (n - r + 1) ** (1 / self.temperature)
            probs.append(score)
        
        # Normalize
        total = sum(probs)
        probs = [p / total for p in probs]
        
        # Select
        selected = random.choices(sorted_pop, weights=probs, k=1)[0]
        
        return selected
    
    def _crossover(
        self,
        parent1: ExperimentVariant,
        parent2: ExperimentVariant,
    ) -> ExperimentVariant:
        """Crossover two parents.
        
        Args:
            parent1: First parent
            parent2: Second parent
            
        Returns:
            Child variant
        """
        import copy
        
        # Create child from parent1 with some elements from parent2
        child_design = copy.deepcopy(parent1.design)
        child_design.id = f"child_{parent1.id}_{parent2.id}"
        
        # Crossover methodology
        if hasattr(parent2.design, 'methodology') and parent2.design.methodology:
            if random.random() < self.crossover_rate:
                if hasattr(child_design, 'methodology'):
                    # Mix methodologies
                    child_design.methodology = (
                        parent1.design.methodology[:len(parent1.design.methodology)//2] +
                        parent2.design.methodology[len(parent2.design.methodology)//2:]
                    )
        
        child = ExperimentVariant(
            design=child_design,
            generation=max(parent1.generation, parent2.generation) + 1,
            parent_ids=[parent1.id, parent2.id],
            mutations=["crossover"],
        )
        
        return child
    
    def _create_next_generation(
        self,
        population: list[ExperimentVariant],
        current_generation: int,
    ) -> list[ExperimentVariant]:
        """Create next generation.
        
        Strategy:
        - Elitism: Keep top 2
        - Crossover: Create 4 children
        - Mutation: Create 2 mutants
        
        Args:
            population: Current population
            current_generation: Current generation number
            
        Returns:
            Next generation population
        """
        # Sort by fitness
        sorted_pop = sorted(population, key=lambda v: v.fitness, reverse=True)
        
        next_gen = []
        
        # Elitism: Keep top 2
        elite_count = min(2, len(sorted_pop))
        for i in range(elite_count):
            elite = sorted_pop[i]
            elite.generation = current_generation + 1
            next_gen.append(elite)
        
        # Crossover: Create 4 children
        while len(next_gen) < elite_count + 4 and len(sorted_pop) >= 2:
            parent1 = self._select_parent(population)
            parent2 = self._select_parent(population)
            
            if parent1.id != parent2.id:
                child = self._crossover(parent1, parent2)
                child.generation = current_generation + 1
                next_gen.append(child)
        
        # Mutation: Fill rest with mutants
        while len(next_gen) < self.population_size:
            base = self._select_parent(population)
            mutant_design = self._mutate_design(base.design, rate=self.mutation_rate)
            mutant_design.id = f"mutant_{base.id}_{len(next_gen)}"
            
            mutant = ExperimentVariant(
                design=mutant_design,
                generation=current_generation + 1,
                parent_ids=[base.id],
                mutations=["mutation"],
            )
            next_gen.append(mutant)
        
        logger.info(f"Created next generation with {len(next_gen)} variants")
        return next_gen
    
    def _has_converged(
        self,
        population: list[ExperimentVariant],
    ) -> bool:
        """Check if population has converged.
        
        Args:
            population: Current population
            
        Returns:
            True if converged
        """
        if len(population) < 2:
            return True
        
        fitnesses = [v.fitness for v in population]
        max_fit = max(fitnesses)
        min_fit = min(fitnesses)
        
        # Check fitness variance
        if max_fit - min_fit < 0.01:
            return True
        
        # Check if best fitness is very high
        if max_fit > 9.5:
            return True
        
        return False


__all__ = [
    "EvolutionaryExperimentSearch",
    "ExperimentVariant",
    "EvolutionResult",
]
